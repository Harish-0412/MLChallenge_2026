"""Additional full script census, bounded examples, and audit output verification."""
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

from audit_dataset import ROOT, dump_json, records, sha256
from normalization import comparison_key

SCRIPTS = ['Devanagari','Bengali','Gujarati','Gurmukhi','Oriya','Tamil','Telugu','Kannada','Malayalam','Arabic','Cyrillic','Han']


def main():
    report_path = ROOT/'reports/eda/full_audit.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not report.get('complete'):
        raise SystemExit('Run the complete audit first')
    con=duckdb.connect(str(ROOT/'data/interim/audit.duckdb'),read_only=True)
    con.execute("SET memory_limit='1GB'")
    con.execute('SET threads=2')
    detail={'script_census':{},'examples':{},'special_codepoint_samples':{}}
    verification={'input_checksums_unchanged':True,'parquet_checks':[],'normalization_sample_checks':[]}
    for item in report['files']:
        if sha256(ROOT/item['file']) != item['sha256']:
            raise AssertionError(f'Input changed: {item["file"]}')
    for table in report['profiles']:
        print(f'SCRIPT CENSUS AND VERIFY {table}',flush=True)
        terms=[]
        for script in SCRIPTS:
            for col,tag in [('business_name','name'),('business_address','address')]:
                terms.append(rf"count_if(regexp_matches({col}, '\p{{{script}}}')) AS {script.lower()}_{tag}")
        detail['script_census'][table]=records(con,f'SELECT country,{",".join(terms)} FROM {table} GROUP BY country ORDER BY country')
        detail['examples'][table]={}
        special=Counter()
        for label,predicate in [
            ('controls',r"regexp_matches(business_name||business_address,'\p{Cc}')"),
            ('formats',r"regexp_matches(business_name||business_address,'\p{Cf}')"),
            ('placeholder_names',"lower(trim(business_name)) IN ('na','n/a','null','none','nan','unknown','-')")]:
            examples=records(con,f'SELECT entity_id,business_name,business_address,country FROM {table} WHERE {predicate} ORDER BY entity_id LIMIT 10')
            detail['examples'][table][label]=examples
            import unicodedata
            for row in examples:
                for char in row['business_name']+row['business_address']:
                    if unicodedata.category(char) in ['Cc','Cf']:
                        special[f'U+{ord(char):04X} {unicodedata.name(char,"UNNAMED")}']+=1
        detail['special_codepoint_samples'][table]=dict(special)
        path=(ROOT/'data/interim'/f'{table}.parquet').as_posix()
        check_sql='''SELECT count(*),sum(hash(entity_id,business_name,business_address,country,name_key,address_key)) FROM {}'''
        left=con.execute(check_sql.format(table)).fetchone()
        right=con.execute(check_sql.format(f"read_parquet('{path}')")).fetchone()
        assert left==right,(table,left,right)
        verification['parquet_checks'].append({'file':table,'rows':right[0],'count_and_row_hash_sum_agree':True})
        sample=records(con,f"""SELECT business_name,business_address,name_key,address_key FROM {table}
            WHERE hash(entity_id)%1000=0 ORDER BY entity_id LIMIT 5000""")
        for row in sample:
            assert comparison_key(row['business_name'])==row['name_key'],(table,row)
            assert comparison_key(row['business_address'])==row['address_key'],(table,row)
        verification['normalization_sample_checks'].append({'file':table,'records_checked':len(sample),'python_sql_agree':True})
        dump_json(ROOT/'reports/eda/text_quality_details.json',detail)
    detail['reference_collision_examples']={}
    for split in ['train','test']:
        detail['reference_collision_examples'][split]=records(con,f'''SELECT t.entity_id,t.business_name,t.business_address,t.country,t.name_key,t.address_key
            FROM {split}_source1 t JOIN
            (SELECT country,name_key,address_key FROM {split}_source1
             GROUP BY country,name_key,address_key HAVING count(*)>1) g
            USING(country,name_key,address_key) ORDER BY entity_id LIMIT 100''')
    dump_json(ROOT/'reports/eda/text_quality_details.json',detail)
    verification['complete']=True
    verification['notes']='Parquet checks compare row counts and aggregate hashes against the audit database; they are not a formal collision-free equality proof. Raw-file SHA-256 was rechecked against pre-import values.'
    dump_json(ROOT/'reports/eda/verification.json',verification)
    con.close()
    print(json.dumps(verification,indent=2),flush=True)


if __name__=='__main__':
    main()
