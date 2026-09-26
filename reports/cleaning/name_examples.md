# Name feature examples

First four rows (by entity ID) per category over all six files: raw name, then the value.

## alias:aka

- S1-107532991: `'Aka Sangh'` -> ` || sangh`
- S1-161416544: `'Aka Holdings'` -> ` || holdings`
- S1-169333577: `'Aka Solution Private Limited'` -> ` || solution`
- S1-210956336: `'Aka Associates'` -> ` || associates`

## alias:dba

- S1-159842053: `'Dba Brothers Partners'` -> ` || brothers partners`
- S1-265930236: `'Dba Chemicals Private Limited'` -> ` || chemicals`
- S1-28578843: `'Dba Services Private Limited'` -> ` || services`
- S1-304445076: `'Dba Technologies Center'` -> ` || technologies center`

## alias:fka

- S1-103057841: `'FKA Electronics Ltd'` -> ` || electronics`
- S1-228290793: `'FKA Club SARL'` -> ` || club`
- S1-572855222: `'FKA Designs Ltd'` -> ` || designs`
- S1-6593701: `'FKA Beaver Private Limited'` -> ` || beaver`

## alias:ta

- S1-138947935: `'T/A Systems Inc.'` -> ` || systems`
- S1-159993402: `'T/A Post Inc.'` -> ` || post`
- S1-199907473: `'T/A Post PLLC'` -> ` || post`
- S1-234259861: `'T/A Post LLC'` -> ` || post`

## alias:trading_as

- S1-270064956: `'Trading As Packaging Private Limited'` -> ` || packaging`
- S2-19661410: `'TRADING AS PACKAGING PRIVATE LIMITED'` -> ` || packaging`
- S2-581919: `'Trading As Packaging Industries Private'` -> ` || packaging industries`
- S3-100006043: `'Evolum Labs trading as Environmental Program LLC'` -> `evolum labs || environmental program`

## domain_like

- S2-100002938: `'route13nails.com'` -> `route13nails | route13nails`
- S2-100003506: `'bharatit.com'` -> `bharatit | bharatit`
- S2-100005970: `'nationalcoalition.com'` -> `nationalcoalition | nationalcoalition`
- S2-100013478: `'goldenapexairport.com'` -> `goldenapexairport | goldenapexairport`

## fallback

- S1-25250464: `'Co & Cie SAS'` -> `co cie sas`
- S1-431622167: `'Limited, LLC'` -> `limited llc`
- S1-536024203: `'Corporation'` -> `corporation`
- S1-556006241: `'Co & Cie'` -> `co cie`

## leading_removed

- S1-100110328: `'The Dent Hypnosis'` -> `the -> dent hypnosis`
- S1-100129135: `'The Dent Tattoo P.C.'` -> `the -> dent tattoo`
- S1-100314123: `'The Dent Hair Studio'` -> `the -> dent hair studio`
- S1-100382222: `'The Dent Cafe'` -> `the -> dent cafe`

## legal_pos:bracket

- S1-115395323: `'Surgical Clinic of Draper City (sl Co)'` -> `CO | surgical clinic of draper city sl`
- S1-131408978: `'Family Group of Bluffdale (sl Co)'` -> `CO | family group of bluffdale sl`
- S1-145355833: `'Bluffdale (sl Co) Tower'` -> `CO | bluffdale sl tower`
- S1-15203265: `'Santaquin City (utah Co) Veterans Pioneer Charities'` -> `CO | santaquin city utah veterans pioneer charities`

## legal_pos:middle

- S1-100207725: `'Crystal Infrastructure Corporation Associates'` -> `CORP | crystal infrastructure associates`
- S1-100306899: `'Brigida Ochoa, P.A. Center'` -> `PA | brigida ochoa center`
- S1-101430134: `'Reinvent & Co Center'` -> `CO | reinvent center`
- S1-101448268: `'Avdic, Evelina M., P.A., M.D., P.C. Partners'` -> `PC+PA | avdic evelina m md partners`

## legal_pos:mixed

- S1-100029574: `'Berget Toran, P.A., DDS PC'` -> `PC+PA | berget toran dds`
- S1-100107727: `'Kushal & Co of Kolkata Private Limited'` -> `PVT+LTD+CO | kushal of kolkata`
- S1-100362203: `'Lp Incubator Pvt Ltd'` -> `PVT+LP+LTD | incubator`
- S1-100833155: `'Jenilee M. Mcwhorter, P.A., M.D., P.C.'` -> `PC+PA | jenilee m mcwhorter md`

## legal_pos:prefix

- S1-106045582: `'CO Equitable'` -> `CO | equitable`
- S1-106694733: `'PC Apex'` -> `PC | apex`
- S1-107512951: `'PA Retail'` -> `PA | retail`
- S1-127385277: `'LP Arc Center'` -> `LP | arc center`

## legal_pos:suffix

- S1-100000221: `'National Redwood LLC'` -> `LLC | national redwood`
- S1-100001013: `'Bordeaux Theatre SARL'` -> `SARL | bordeaux theatre`
- S1-100001295: `'Établissements Confrerie SCI'` -> `SCI | établissements confrerie`
- S1-100001512: `'South Ventures Pvt Ltd'` -> `PVT+LTD | south ventures`

## placeholder

- S2-102598836: `'Na'` -> `na`
- S2-109029910: `'NA'` -> `na`
- S2-10975227: `'NA'` -> `na`
- S2-156787089: `'NA'` -> `na`

## trim_changes

- S1-100003037: `'Services Om Services Private Limited'` -> `services om services -> services om`
- S1-100008286: `'Al Services Private Limited'` -> `al services -> al`
- S1-100011625: `'Bilaungi Infratech Private Limited'` -> `bilaungi infratech -> bilaungi`
- S1-100018120: `'Future Services Private Limited'` -> `future services -> future`
