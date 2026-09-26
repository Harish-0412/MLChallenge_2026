# Address extraction sample (feat_v2_0)

30 non-missing addresses per country x source, ordered by hash(entity_id) (deterministic). For hand review: the raw address, the canonical segments, state (confidence), number spans (raw -> canon | context), postal candidates, city candidates, removed injected components and the parse confidence. Review notes are at the end of the file.

## France - source 1

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S1-605167031 (test) | 30 bis Rue René Delissen, Dunkerque, Hauts-de-France | 30 bis rue rene delissen ; dunkerque ; hauts de france | hauts de france (exact) | 30 bis -> 30bis | - | dunkerque | - | high |
| S1-907915622 (test) | 7 Rue Balzac, Tourcoing, Hauts-de-France | 7 rue balzac ; tourcoing ; hauts de france | hauts de france (exact) | 7 -> 7 | - | tourcoing | - | high |
| S1-490704084 (test) | Pays de la Loire, 13 Avenue du Printemps, Nantes | pays de la loire ; 13 avenue du printemps ; nantes | pays de la loire (exact) | 13 -> 13 | - | nantes | - | high |
| S1-521658054 (test) | 20 Allée de la Traine, Lège-Cap-Ferret, Nouvelle-Aquitaine | 20 allee de la traine ; lege cap ferret ; nouvelle aquitaine | nouvelle aquitaine (exact) | 20 -> 20 | - | lege cap ferret | - | high |
| S1-460092328 (test) | 26 Boulevard d'Halluin, Tourcoing, Hauts-de-France | 26 boulevard d halluin ; tourcoing ; hauts de france | hauts de france (exact) | 26 -> 26 | - | tourcoing | - | high |
| S1-440370897 (test) | 9 RUE Pierre Loti, Bordeaux, Nouvelle-Aquitaine | 9 rue pierre loti ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 9 -> 9 | - | bordeaux | - | high |
| S1-722314419 (test) | 2 Allée Jorge Semprùn, Pessac, Nouvelle-Aquitaine | 2 allee jorge semprun ; pessac ; nouvelle aquitaine | nouvelle aquitaine (exact) | 2 -> 2 | - | pessac | - | high |
| S1-234448321 (test) | Nouvelle-Aquitaine, Bordeaux, 18 Place de l'Église Saint-Augustin | nouvelle aquitaine ; bordeaux ; 18 place de l eglise saint augustin | nouvelle aquitaine (exact) | 18 -> 18 | - | bordeaux | - | high |
| S1-733256165 (test) | 18 Rue Paul Valéry, Bordeaux, Nouvelle-Aquitaine | 18 rue paul valery ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 18 -> 18 | - | bordeaux | - | high |
| S1-192991064 (test) | 9 Rue Quintin, Bordeaux, Nouvelle-Aquitaine | 9 rue quintin ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 9 -> 9 | - | bordeaux | - | high |
| S1-129096196 (test) | 36 RUE DE TAUZIA, LE CLOS MONTESQUIEU, Bordeaux, Nouvelle-Aquitaine | 36 rue de tauzia ; le clos montesquieu ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 36 -> 36 | - | bordeaux ; le clos montesquieu | - | high |
| S1-257178650 (test) | 104 Avenue de Noès, Pessac, Nouvelle-Aquitaine | 104 avenue de noes ; pessac ; nouvelle aquitaine | nouvelle aquitaine (exact) | 104 -> 104 | - | pessac | - | high |
| S1-349511242 (test) | 20 Rue des Frères Lumière, Tourcoing, Hauts-de-France | 20 rue des freres lumiere ; tourcoing ; hauts de france | hauts de france (exact) | 20 -> 20 | - | tourcoing | - | high |
| S1-469181774 (test) | 70 Avenue Carnot, Nouvelle-Aquitaine, Mérignac | 70 avenue carnot ; nouvelle aquitaine ; merignac | nouvelle aquitaine (exact) | 70 -> 70 | - | merignac | - | high |
| S1-448706949 (test) | 284 RUE Mollien, Calais, Hauts-de-France | 284 rue mollien ; calais ; hauts de france | hauts de france (exact) | 284 -> 284 | - | calais | - | high |
| S1-87517302 (test) | 215 Rue des 4 Coins, Calais, Hauts-de-France | 215 rue des 4 coins ; calais ; hauts de france | hauts de france (exact) | 215 -> 215 ; 4 -> 4 (rue des) | - | calais | - | high |
| S1-361430847 (test) | 2 Allée des Troves, La Baule-Escoublac, Pays de la Loire | 2 allee des troves ; la baule escoublac ; pays de la loire | pays de la loire (exact) | 2 -> 2 | - | la baule escoublac | - | high |
| S1-887019587 (test) | 16 RUE de Pas, Restaurant Clement Marot, Lille, Hauts-de-France | 16 rue de pas ; restaurant clement marot ; lille ; hauts de france | hauts de france (exact) | 16 -> 16 | - | lille ; restaurant clement marot | - | high |
| S1-895112023 (test) | 14 COUR2 DE L INTENDANCE, Bordeaux, Nouvelle-Aquitaine | 14 cour2 de l intendance ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 14 -> 14 | - | bordeaux | - | high |
| S1-719084241 (test) | 37 Rue Jac Belaubre, Bordeaux, Nouvelle-Aquitaine | 37 rue jac belaubre ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 37 -> 37 | - | bordeaux | - | high |
| S1-472200064 (test) | Pays de la Loire, 16 Impasse de la Terre Adélie, Nantes | pays de la loire ; 16 impasse de la terre adelie ; nantes | pays de la loire (exact) | 16 -> 16 | - | nantes | - | high |
| S1-569521939 (test) | Hauts-de-France, 44 Rue du Général Douay, Tourcoing | hauts de france ; 44 rue du general douay ; tourcoing | hauts de france (exact) | 44 -> 44 | - | tourcoing | - | high |
| S1-691397583 (test) | Calais, Hauts-de-France, 95 Rue des Salines | calais ; hauts de france ; 95 rue des salines | hauts de france (exact) | 95 -> 95 | - | calais | - | high |
| S1-753036812 (test) | 3 Avenue des Gazons, Nantes, Pays de la Loire | 3 avenue des gazons ; nantes ; pays de la loire | pays de la loire (exact) | 3 -> 3 | - | nantes | - | high |
| S1-486496357 (test) | 79 Chaussée Pierre Curie, Tourcoing, Hauts-de-France | 79 chaussee pierre curie ; tourcoing ; hauts de france | hauts de france (exact) | 79 -> 79 | - | tourcoing | - | high |
| S1-366471958 (test) | 32 Rue Édouard Branly, Bordeaux, Nouvelle-Aquitaine | 32 rue edouard branly ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 32 -> 32 | - | bordeaux | - | high |
| S1-311058285 (test) | 51 Rue Francia, Calais, Hauts-de-France | 51 rue francia ; calais ; hauts de france | hauts de france (exact) | 51 -> 51 | - | calais | - | high |
| S1-539591853 (test) | 94 Rue Francin, Nouvelle-Aquitaine, Bordeaux | 94 rue francin ; nouvelle aquitaine ; bordeaux | nouvelle aquitaine (exact) | 94 -> 94 | - | bordeaux | - | high |
| S1-512974500 (test) | 12 RUE Lyderic, Lille, Hauts-de-France | 12 rue lyderic ; lille ; hauts de france | hauts de france (exact) | 12 -> 12 | - | lille | - | high |
| S1-225624959 (test) | Nantes, 25 Rue Docteur Brindeau, Pays de la Loire | nantes ; 25 rue docteur brindeau ; pays de la loire | pays de la loire (exact) | 25 -> 25 | - | nantes | - | high |
## France - source 2

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S2-52395060 (test) | 6 BOULEVARD DES BATISSEURS, ROUBAIX | 6 boulevard des batisseurs ; roubaix | - (none) | 6 -> 6 | - | roubaix | - | medium |
| S2-811959365 (test) | NO 19 R CHARLES JOSSE, ST.-HERBLAIN | 19 rue charles josse ; saint herblain | - (none) | 19 -> 19 (no) | - | saint herblain | - | medium |
| S2-574092423 (test) | Gironde, (4) R. LOUIS BERON, MÉRIGNAC | nouvelle aquitaine ; 4 rue louis beron ; merignac | nouvelle aquitaine (mapped_department) | 4 -> 4 | - | merignac | - | high |
| S2-715003546 (test) | 188 COURS DE L'YSER, BORDEAUX, Gironde | 188 cours de l yser ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (mapped_department) | 188 -> 188 | - | bordeaux | - | high |
| S2-741841262 (test) | N°5 CHEMIN DU MOULIN DE DUTRUCH, LA TESTE DE BUCH, Nouvelle-Aquitaine | 5 chemin du moulin de dutruch ; la teste de buch ; nouvelle aquitaine | nouvelle aquitaine (exact) | 5 -> 5 (no) | - | la teste de buch | - | high |
| S2-631614054 (test) | 10 COUR DELATTRE, LILLE, Hauts-de-France | 10 cour delattre ; lille ; hauts de france | hauts de france (exact) | 10 -> 10 | - | lille | - | high |
| S2-870972471 (test) | 19 R. MARCILIN BERTHELOT, MERIGNAC, Gironde | 19 rue marcilin berthelot ; merignac ; nouvelle aquitaine | nouvelle aquitaine (mapped_department) | 19 -> 19 | - | merignac | - | high |
| S2-503822002 (test) | 3 C PL DANTON, NANTES, Loire-Atlantique | 3 c pl danton ; nantes ; pays de la loire | pays de la loire (mapped_department) | 3 -> 3 | - | nantes | - | high |
| S2-67605626 (test) | 159 RUE ÉMILE COMBES, MÉRIGNAC | 159 rue emile combes ; merignac | - (none) | 159 -> 159 | - | merignac | - | medium |
| S2-297466377 (test) | 108 BOULEVARD MICHELET, NANTES, Loire-Atlantique | 108 boulevard michelet ; nantes ; pays de la loire | pays de la loire (mapped_department) | 108 -> 108 | - | nantes | - | high |
| S2-834922092 (test) | N° 44 R DU PAS NICOALS, SAINT-NAZAIRE, Loire-Atlantique | 44 rue du pas nicoals ; saint nazaire ; pays de la loire | pays de la loire (mapped_department) | 44 -> 44 (no) | - | saint nazaire | - | high |
| S2-655307173 (test) | Hauts-de-France, Lille, 92 R DU VINGTIEME SIECLE | hauts de france ; lille ; 92 rue du vingtieme siecle | hauts de france (exact) | 92 -> 92 | - | lille | - | high |
| S2-307486718 (test) | NO 31 RUE GAMBENTA, DUNKERQUE, Nord | 31 rue gambenta ; dunkerque ; hauts de france | hauts de france (mapped_department) | 31 -> 31 (no) | - | dunkerque | - | high |
| S2-695699164 (test) | 23 PL DU MARECHAL LECLERC, LILLE, Hauts-de-France | 23 pl du marechal leclerc ; lille ; hauts de france | hauts de france (exact) | 23 -> 23 | - | lille | - | high |
| S2-280118000 (test) | 94 RUE DU TONDU, BORDEAUX, Gironde | 94 rue du tondu ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (mapped_department) | 94 -> 94 | - | bordeaux | - | high |
| S2-55688828 (test) | 0095 DGIUE DE MER, Dunkerque, Nord | 95 dgiue de mer ; dunkerque ; hauts de france | hauts de france (mapped_department) | 0095 -> 95 | - | dunkerque | - | high |
| S2-274317034 (test) | 051 R DE MADAGASCAR, LILLE | 51 rue de madagascar ; lille | - (none) | 051 -> 51 | - | lille | - | medium |
| S2-478433926 (test) | LA TESTE-DE-BUCH, 39 ALL. RAYMOND DAUGEY CAZAUX | la teste de buch ; 39 allee raymond daugey cazaux | - (none) | 39 -> 39 | - | la teste de buch | - | medium |
| S2-123931721 (test) | 43 RUE DU MARAIS, LILLE, Nord | 43 rue du marais ; lille ; hauts de france | hauts de france (mapped_department) | 43 -> 43 | - | lille | - | high |
| S2-478675389 (test) | 32 R DE MALMY, Pornic | 32 rue de malmy ; pornic | - (none) | 32 -> 32 | - | pornic | - | medium |
| S2-461859531 (test) | 1 R RAEAU, Bordeaux, Nouvelle-Aquitaine | 1 rue raeau ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 1 -> 1 | - | bordeaux | - | high |
| S2-552941032 (test) | Loire-Atlantique, 2 TER ALLEE DES VIOLETTES, LA BAULE-ESCOUBLAC | pays de la loire ; 2 ter allee des violettes ; la baule escoublac | pays de la loire (mapped_department) | 2 TER -> 2ter | - | la baule escoublac | - | high |
| S2-514690298 (test) | 32 RUE ERNEST DECONYNCK, LILLE, Hauts-de-France | 32 rue ernest deconynck ; lille ; hauts de france | hauts de france (exact) | 32 -> 32 | - | lille | - | high |
| S2-209859958 (test) | # 1 ALLÉE MICHEL CROZ, NANTES, Loire-Atlantique | 1 allee michel croz ; nantes ; pays de la loire | pays de la loire (mapped_department) | 1 -> 1 | - | nantes | - | high |
| S2-119714923 (test) | LÈGE-CAP-FERRET, Gironde, 60 AVE DU GENERAL DE GAULLE | lege cap ferret ; nouvelle aquitaine ; 60 avenue du general de gaulle | nouvelle aquitaine (mapped_department) | 60 -> 60 | - | lege cap ferret | - | high |
| S2-40231678 (test) | 19 R. DES PINS VERTS, LA TESTE-DE-BUCH | 19 rue des pins verts ; la teste de buch | - (none) | 19 -> 19 | - | la teste de buch | - | medium |
| S2-6835370 (test) | 122 BOULEVARD DE LA LIBERTE, LILLE, Nord | 122 boulevard de la liberte ; lille ; hauts de france | hauts de france (mapped_department) | 122 -> 122 | - | lille | - | high |
| S2-476581970 (test) | IMP. DE LA CARRÉE, Saint-Herblain, Loire-Atlantique | impasse de la carree ; saint herblain ; pays de la loire | pays de la loire (mapped_department) | - | - | saint herblain | - | medium |
| S2-571992349 (test) | SAINT-NAZAIRE, 31 RUE DES AJONCS | saint nazaire ; 31 rue des ajoncs | - (none) | 31 -> 31 | - | saint nazaire | - | medium |
| S2-266280774 (test) | 48 CITE CASSEVILLE, LILLE, Nord | 48 cite casseville ; lille ; hauts de france | hauts de france (mapped_department) | 48 -> 48 | - | lille | - | high |
## France - source 3

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S3-545178526 (test) | 183 Rue Des Stations, Lille, Nord | 183 rue des stations ; lille ; hauts de france | hauts de france (mapped_department) | 183 -> 183 | - | lille | - | high |
| S3-392762597 (test) | 19 R. Gustave Jolivet, Lille, Nord | 19 rue gustave jolivet ; lille ; hauts de france | hauts de france (mapped_department) | 19 -> 19 | - | lille | - | high |
| S3-194130855 (test) | 88 Cours Aristide Briand, Bordeaux, Nouvelle-Aquitaine | 88 cours aristide briand ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 88 -> 88 | - | bordeaux | - | high |
| S3-306258793 (test) | 55 Chemin Tournerond, Nantes | 55 chemin tournerond ; nantes | - (none) | 55 -> 55 | - | nantes | - | medium |
| S3-575627374 (test) | 53 Rue Du Prbsident Wilson, Dunkerque, Nord | 53 rue du prbsident wilson ; dunkerque ; hauts de france | hauts de france (mapped_department) | 53 -> 53 | - | dunkerque | - | high |
| S3-486353838 (test) | No 32 Ave Jean Paul Marat, Saint-herblain, Loire-Atlantique | 32 avenue jean paul marat ; saint herblain ; pays de la loire | pays de la loire (mapped_department) | 32 -> 32 (no) | - | saint herblain | - | high |
| S3-514800222 (test) | 65 Rue Marcel Hénaux, Tourcoing | 65 rue marcel henaux ; tourcoing | - (none) | 65 -> 65 | - | tourcoing | - | medium |
| S3-113316365 (test) | 18 Bis Rue Dubourdieu, Bordeaux, Gironde | 18 bis rue dubourdieu ; bordeaux ; nouvelle aquitaine | nouvelle aquitaine (mapped_department) | 18 Bis -> 18bis | - | bordeaux | - | high |
| S3-354726198 (test) | 94 Rue Des Stations, Appartement 231, Lille | 94 rue des stations ; appartement 231 ; lille | - (none) | 94 -> 94 ; 231 -> 231 (appartement) | - | lille | - | medium |
| S3-281860184 (test) | 15 Bis Avenue Nungesser, Pays de la Loire, Nantes | 15 bis avenue nungesser ; pays de la loire ; nantes | pays de la loire (exact) | 15 Bis -> 15bis | - | nantes | - | high |
| S3-700363168 (test) | N°11 R Edmond Besse, Bordeaux | 11 rue edmond besse ; bordeaux | - (none) | 11 -> 11 (no) | - | bordeaux | - | medium |
| S3-442335286 (test) | R De Thumesnil, Lille, Nord | rue de thumesnil ; lille ; hauts de france | hauts de france (mapped_department) | - | - | lille | - | medium |
| S3-480235138 (test) | Nord, 162 R. D'isly, Lille | hauts de france ; 162 rue d isly ; lille | hauts de france (mapped_department) | 162 -> 162 | - | lille | - | high |
| S3-463942102 (test) | 89 - Rue Du Grand Maurian, Bordeaux | 89 rue du grand maurian ; bordeaux | - (none) | 89 -> 89 | - | bordeaux | - | medium |
| S3-122908768 (test) | 95 Route Du Cap Ferret, Lège-cap-ferret, Nouvelle-Aquitaine | 95 route du cap ferret ; lege cap ferret ; nouvelle aquitaine | nouvelle aquitaine (exact) | 95 -> 95 | - | lege cap ferret | - | high |
| S3-492762644 (test) | Nord, 54 Rue Ferrer, Lille | hauts de france ; 54 rue ferrer ; lille | hauts de france (mapped_department) | 54 -> 54 | - | lille | - | high |
| S3-35890280 (test) | 003 Blvd Lelasseur, Nantes, Loire-Atlantique | 3 boulevard lelasseur ; nantes ; pays de la loire | pays de la loire (mapped_department) | 003 -> 3 | - | nantes | - | high |
| S3-602677768 (test) | No 27 Rue Louguet, Calais | 27 rue louguet ; calais | - (none) | 27 -> 27 (no) | - | calais | - | medium |
| S3-221912711 (test) | 51 R De Jemmapes, Lille | 51 rue de jemmapes ; lille | - (none) | 51 -> 51 | - | lille | - | medium |
| S3-273100376 (test) | La Teste-de-Buch, 29 Route du Lac Cazaux, Nouvelle-Aquitaine | la teste de buch ; 29 route du lac cazaux ; nouvelle aquitaine | nouvelle aquitaine (exact) | 29 -> 29 | - | la teste de buch | - | high |
| S3-647648928 (test) | 0054 Av Des Ectoppes, Pessac, Nouvelle-Aquitaine | 54 avenue des ectoppes ; pessac ; nouvelle aquitaine | nouvelle aquitaine (exact) | 0054 -> 54 | - | pessac | - | high |
| S3-274918364 (test) | Rue De Psesac, Nouvelle-Aquitaine, Bordeaux | rue de psesac ; nouvelle aquitaine ; bordeaux | nouvelle aquitaine (exact) | - | - | bordeaux | - | medium |
| S3-819876881 (test) | Nantes, 3 R. Du Cherche Midi | nantes ; 3 rue du cherche midi | - (none) | 3 -> 3 | - | nantes | - | medium |
| S3-735065404 (test) | # 19 R. Saint Jacques, Lille | 19 rue saint jacques ; lille | - (none) | 19 -> 19 | - | lille | - | medium |
| S3-297537689 (test) | 12 Rue De La Pavotière, Nantes | 12 rue de la pavotiere ; nantes | - (none) | 12 -> 12 | - | nantes | - | medium |
| S3-521724596 (test) | Lille, 6 Rue Du Dieu De Marcq | lille ; 6 rue du dieu de marcq | - (none) | 6 -> 6 | - | lille | - | medium |
| S3-872793708 (test) | 54 R. De La Planche Au Gue, Nantes, Pays de la Loire | 54 rue de la planche au gue ; nantes ; pays de la loire | pays de la loire (exact) | 54 -> 54 | - | nantes | - | high |
| S3-783809527 (test) | 6 R Des Fusilles, Dunkerque | 6 rue des fusilles ; dunkerque | - (none) | 6 -> 6 | - | dunkerque | - | medium |
| S3-866905828 (test) | No 97 Rp Des Droits De L'homme, Calais, Hauts-de-France | 97 rp des droits de l homme ; calais ; hauts de france | hauts de france (exact) | 97 -> 97 (no) | - | calais | - | high |
| S3-509853941 (test) | 48 Rue Piere Loti, La Teste-de-Buch, Nouvelle-Aquitaine | 48 rue piere loti ; la teste de buch ; nouvelle aquitaine | nouvelle aquitaine (exact) | 48 -> 48 | - | la teste de buch | - | high |
## India - source 1

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S1-186322860 (train) | F-65 Gali No 1, Mohan Baba Nagar, Tajpur Road Badarpur Border, New Delhi, South Delhi, Delhi | f 65 gali 1 ; mohan baba nagar ; tajpur road badarpur border ; new delhi ; south delhi ; delhi | delhi (exact) | F-65 -> f65 ; 1 -> 1 (gali no) | - | south delhi ; new delhi ; mohan baba nagar | - | high |
| S1-947549750 (train) | H. No 10-29/3, Part Plot No. 28, Balaji Colony, Gayathri Nagar, Saroornagar, K.V.Rangareddy, Telangana | h 10 29 3 ; part plot 28 ; balaji colony ; gayathri nagar ; saroornagar ; k v rangareddy ; telangana | telangana (exact) | 10-29/3 -> 10-29/3 (h no) ; 28 -> 28 (plot no) | - | k v rangareddy ; saroornagar ; gayathri nagar | - | high |
| S1-546088573 (test) | C/O Dilip Poddar, Kalyan Nagar Jahaj Bari, North 24 Parganas, West Bengal | c o dilip poddar ; kalyan nagar jahaj bari ; north 24 parganas ; west bengal | west bengal (exact) | 24 -> 24 (north) | - | kalyan nagar jahaj bari ; c o dilip poddar | - | high |
| S1-156619671 (train) | Pranayam Resident Welfare Assoc.(Regd.) Flat No. D-4-1003, Sector 82, Faridabad, Haryana | pranayam resident welfare assoc regd flat no d 4 1003 ; sector 82 ; faridabad ; haryana | haryana (exact) | D-4-1003 -> d4-1003 (flat no) ; 82 -> 82 (sector) | - | faridabad | - | high |
| S1-225444618 (train) | 2Nd Floor, Maharashtra, Plot 119, Manjulabai Jethabai Building Dadi Seth Agairy Lane, Chirabazar, Kalba, Devi, Mumbai City, Mumbai | 2nd floor ; maharashtra ; plot 119 ; manjulabai jethabai building dadi seth agairy lane ; chirabazar ; kalba ; devi ; mumbai city ; mumbai | maharashtra (exact) | 119 -> 119 (plot) | - | chirabazar ; kalba ; devi | - | high |
| S1-553286477 (train) | 4Th Cross, Chikkadugodi, Tavarekere, No 94/26, Bangalore, Karnataka | 4th cross ; chikkadugodi ; tavarekere ; 94 26 ; bangalore ; karnataka | karnataka (exact) | 94/26 -> 94/26 (no) | - | bangalore ; tavarekere ; chikkadugodi | - | high |
| S1-167300836 (train) | Jhansi, Opposite M L B Medical Collegejhansi Jhansi, Uttar Pradesh | jhansi ; opposite m l b medical collegejhansi jhansi ; uttar pradesh | uttar pradesh (exact) | - | - | jhansi | - | medium |
| S1-243675239 (train) | B-205, Indraprastha, Indralok Chs Ltd., Sector-4, Pot Nos 27/76/77, New Panvel, Mumbai, Mumbai City, Maharashtra | b 205 ; indraprastha ; indralok chs ltd ; sector 4 ; pot nos 27 76 77 ; new panvel ; mumbai ; mumbai city ; maharashtra | maharashtra (exact) | B-205 -> b205 ; 4 -> 4 (sector) ; 27/76/77 -> 27/76/77 (pot nos) | - | mumbai city ; mumbai ; new panvel | - | high |
| S1-536549350 (train) | 701, 7Th Floor, Plot 365, Omkar Niwas, Kw Chitale P, Mumbai, Maharashtra | 701 ; 7th floor ; plot 365 ; omkar niwas ; kw chitale p ; mumbai ; maharashtra | maharashtra (exact) | 701 -> 701 ; 365 -> 365 (plot) | - | mumbai ; kw chitale p ; omkar niwas | - | high |
| S1-315989107 (train) | 303, Floor-3Rd, Plot -11/15, Regal Diamond Centre, Tata Road No. 1, Girgaon, Mumbai City, Maharashtra | 303 ; floor 3rd ; plot 11 15 ; regal diamond centre ; tata road 1 ; girgaon ; mumbai city ; maharashtra | maharashtra (exact) | 303 -> 303 ; 11/15 -> 11/15 (plot) ; 1 -> 1 (road no) | - | mumbai city ; girgaon ; regal diamond centre | - | high |
| S1-630551896 (train) | Flat No. 102, H.No.7-1-61/32 &33-121 & 122/3Rt, Sai Laksmi Nilayam, Opposite To Water Suppliers, Khairatabad, Hyderabad, Telangana | flat 102 ; h 7 1 61 32 33 121 122 3rt ; sai laksmi nilayam ; opposite to water suppliers ; khairatabad ; hyderabad ; telangana | telangana (exact) | 102 -> 102 (flat no) ; 7-1-61/32 -> 7-1-61/32 (h no) ; 33-121 -> 33-121 (61 32) ; 122 -> 122 (33 121) | - | hyderabad ; khairatabad ; sai laksmi nilayam | - | high |
| S1-150558239 (test) | Lakshya, Kumarara, Mahishadal, Nandakumar, East Midnapore, West Bengal | lakshya ; kumarara ; mahishadal ; nandakumar ; east midnapore ; west bengal | west bengal (exact) | - | - | east midnapore ; nandakumar ; mahishadal | - | medium |
| S1-758127255 (train) | Flat. No-303, Indira Towers, Mig-424, 425, 1St, 2Nd Nd Phase, Kphb Colony, Tirumalagiri, Hyderabad, Telangana | flat 303 ; indira towers ; mig 424 ; 425 ; 1st ; 2nd nd phase ; kphb colony ; tirumalagiri ; hyderabad ; telangana | telangana (exact) | No-303 -> no303 (flat) ; 424 -> 424 (mig) ; 425 -> 425 | - | hyderabad ; tirumalagiri ; kphb colony | - | high |
| S1-356542957 (train) | #50-B, Kadakola Industrial, Area, Kadakola, Mysore, Karnataka | 50 b ; kadakola industrial ; area ; kadakola ; mysore ; karnataka | karnataka (exact) | 50 -> 50 | - | mysore ; kadakola ; area | - | high |
| S1-946549021 (train) | 14, 1St Cross, 1St Main, Bhcs Layout, Banagirinagar, Bangalore South, Bangalore, Karnataka | 14 ; 1st cross ; 1st main ; bhcs layout ; banagirinagar ; bangalore south ; bangalore ; karnataka | karnataka (exact) | 14 -> 14 | - | bangalore ; bangalore south ; banagirinagar | - | high |
| S1-925931476 (train) | 4/A, Floor - Grd, Recondo Compound, Sudam Kalu Ahire Marg, Glaxo, Worli Colo, Ny, Mumbai, Mumbai City, Maharashtra | 4 a ; floor grd ; recondo compound ; sudam kalu ahire marg ; glaxo ; worli colo ; ny ; mumbai ; mumbai city ; maharashtra | maharashtra (exact) | 4 -> 4 | - | mumbai city ; mumbai ; ny | - | high |
| S1-848124593 (test) | Unit 58, Jagat Satguru Ind Estate, P P L Goregaon East, Off. Aarey Road, Mumbai, Mumbai City, Maharashtra | unit 58 ; jagat satguru ind estate ; p p l goregaon east ; off aarey road ; mumbai ; mumbai city ; maharashtra | maharashtra (exact) | 58 -> 58 (unit) | - | mumbai city ; mumbai ; jagat satguru ind estate | - | high |
| S1-502336499 (test) | 3Rd Floor, N.K.House, Behind : Femina Town Opp. Mirch Masala Hotel, C.G.Road, Nav, Rangpura, Ahmedabad, Gujarat | 3rd floor ; n k house ; behind femina town opp mirch masala hotel ; c g road ; nav ; rangpura ; ahmedabad ; gujarat | gujarat (exact) | - | - | ahmedabad ; rangpura ; nav | - | medium |
| S1-168672557 (test) | Shop No.153, Tm Complex, Near Cheekod Panjayath, Ernad, Malappuram, Malapuram, Kerala | shop 153 ; tm complex ; near cheekod panjayath ; ernad ; malappuram ; malapuram ; kerala | kerala (exact) | 153 -> 153 (shop no) | - | malapuram ; malappuram ; ernad | - | high |
| S1-706395516 (test) | Karnataka, C Block, Sapthagiri Sandalwood, Belathur Main Road, Kumbena Agrahara, Krishnarajapuram, Kadugodi, No. 303, Bangalore, Bangalore South | karnataka ; c block ; sapthagiri sandalwood ; belathur main road ; kumbena agrahara ; krishnarajapuram ; kadugodi ; 303 ; bangalore ; bangalore south | karnataka (exact) | 303 -> 303 (no) | - | sapthagiri sandalwood ; kumbena agrahara ; krishnarajapuram | - | high |
| S1-393295267 (train) | C-50, Siwad Area, Bapu Nagar, Jaipur, Rajasthan | c 50 ; siwad area ; bapu nagar ; jaipur ; rajasthan | rajasthan (exact) | C-50 -> c50 | - | jaipur ; bapu nagar ; siwad area | - | high |
| S1-711687117 (test) | 39B Gorosthan Lane, 3Rd Floor, Kolkata, Kolkata, Howrah, West Bengal | 39b gorosthan lane ; 3rd floor ; kolkata ; kolkata ; howrah ; west bengal | west bengal (exact) | 39B -> 39b | - | howrah ; kolkata | - | high |
| S1-221738170 (test) | Mumbai, Maharashtra, 1 Nichani Kutir1St Floor Juhu Tara Juhu, Mumbai | mumbai ; maharashtra ; 1 nichani kutir1st floor juhu tara juhu ; mumbai | maharashtra (exact) | 1 -> 1 | - | mumbai | - | high |
| S1-462504029 (train) | C/O Suman Kr, Kishanpur, Road, W-04, Supaul, Supaul, Saharsa, Bihar | c o suman kr ; kishanpur ; road ; w 4 ; supaul ; supaul ; saharsa ; bihar | bihar (exact) | W-04 -> w4 | - | saharsa ; supaul ; kishanpur | - | high |
| S1-980156644 (train) | 25, Floor-3, Plot-64, Laher Mulla Trust Building, Gokhale Road (North), Portugese Church, Dadar(W), Mumbai, Maharashtra | 25 ; floor 3 ; plot 64 ; laher mulla trust building ; gokhale road north ; portugese church ; dadar w ; mumbai ; maharashtra | maharashtra (exact) | 25 -> 25 ; 3 -> 3 (floor) ; 64 -> 64 (plot) | - | mumbai ; dadar w ; portugese church | - | high |
| S1-817609851 (train) | E-57, Anushaktinagar, Nr Nutan School, New Sama Road, Vadodara, Gujarat | e 57 ; anushaktinagar ; nr nutan school ; new sama road ; vadodara ; gujarat | gujarat (exact) | E-57 -> e57 | - | vadodara ; nr nutan school ; anushaktinagar | - | high |
| S1-345375933 (test) | A-114 Ground Floor Priyadarshini Vihar, Laxmi Nagar, New Delhi, Delhi | a 114 ground floor priyadarshini vihar ; laxmi nagar ; new delhi ; delhi | delhi (exact) | A-114 -> a114 | - | new delhi ; laxmi nagar | - | high |
| S1-426179592 (train) | Plot No-1, Haldoni More Near Bus Stop, Greater Noida, Gautam Buddha Nagar, Uttar Pradesh | plot 1 ; haldoni more near bus stop ; greater noida ; gautam buddha nagar ; uttar pradesh | uttar pradesh (exact) | No-1 -> no1 (plot) | - | gautam buddha nagar ; greater noida | - | high |
| S1-409248527 (train) | 213/25, Shubharambh Society, Gorai-2, Borivli (West), Mumbai, Maharashtra | 213 25 ; shubharambh society ; gorai 2 ; borivli west ; mumbai ; maharashtra | maharashtra (exact) | 213/25 -> 213/25 ; 2 -> 2 (gorai) | - | mumbai ; borivli west ; shubharambh society | - | high |
| S1-641492300 (train) | H No 8-3-229/D/1/24, Sravanthi Nagar, Road No.10 Extn, Jubilee Hills, Hyderabad, Telangana | h 8 3 229 d 1 24 ; sravanthi nagar ; road 10 extn ; jubilee hills ; hyderabad ; telangana | telangana (exact) | 8-3-229 -> 8-3-229 (h no) ; 1/24 -> 1/24 (229 d) ; 10 -> 10 (road no) | - | hyderabad ; jubilee hills ; sravanthi nagar | - | high |
## India - source 2

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S2-176947873 (test) | FIRT FLOOR D-16 SEC-16, GHAZIABD, NOIDA, Uttar Pradesh | firt floor d 16 sec 16 ; ghaziabd ; noida ; uttar pradesh | uttar pradesh (exact) | D-16 -> d16 (firt floor) ; 16 -> 16 (16 sec) | - | noida ; ghaziabd | - | high |
| S2-723729273 (train) | NO119, KN078, HANUMANTH NAGAR, BANGALROE NORTH, NULL, ಕರ್ನಾಟಕ | no119 ; kn78 ; hanumanth nagar ; bangalroe north ; karnataka | karnataka (mapped_native) | - | - | bangalroe north ; hanumanth nagar | - / nulls 1 | medium |
| S2-666396404 (train) | FLAT NO. A-2-2, SHAMA APARTMENTS PLOT NO. 32, SECTOR-10, DWARKA, DELHI, Delhi | flat no a 2 2 ; shama apartments plot 32 ; sector 10 ; dwarka ; delhi ; delhi | delhi (exact) | A-2-2 -> a2-2 (flat no) ; 32 -> 32 (plot no) ; 10 -> 10 (sector) | - | dwarka | - | high |
| S2-455824000 (test) | NO 826 F 34, VIDYA GROUP, APPARTMENT NO. 8, B6, ASHOK VIHAR PHASE III, KHED SHIVAPUR, GURGAON, Haryana | 826 f 34 ; vidya group ; appartment 8 ; b6 ; ashok vihar phase iii ; khed shivapur ; gurgaon ; haryana | haryana (exact) | 826 -> 826 (no) ; F 34 -> f34 (no 826) ; 8 -> 8 (appartment no) ; B6 -> b6 | - | gurgaon ; khed shivapur ; vidya group | - | high |
| S2-581185018 (train) | SIVAKASI, AYYAN COMPLEX OPPOSITE TO BUS STAND, 14/10, தமிழ்நாடு, VIRUDHUNAGAR | sivakasi ; ayyan complex opposite to bus stand ; 14 10 ; tamil nadu ; virudhunagar | tamil nadu (mapped_native) | 14/10 -> 14/10 | - | virudhunagar ; sivakasi | - | high |
| S2-403279088 (train) | P024 NALHATI PURBA BAZAR, BIRBHUM, পশ্চিমবঙ্গ | p24 nalhati purba bazar ; birbhum ; west bengal | west bengal (mapped_native) | P024 -> p24 | - | birbhum | - | high |
| S2-833387350 (train) | H.NO 57/ VILLAGE KHANDSA, ANJANA COLONY MANESAR GURUGRAM, GURUGRAM, GURGAON, हरियाणा | h 57 village khandsa ; anjana colony manesar gurugram ; gurugram ; gurgaon ; haryana | haryana (mapped_native) | 57 -> 57 (h no) | - | gurgaon ; gurugram ; anjana colony manesar gurugram | - | high |
| S2-555593902 (test) | 822 L WING, COUNTRY PARK PHASE III, OPP TATA STEEL, DATTAPADA ROAD, BORIVALI EAST, BORIVLAI EAST, MUMBAI SUBURBAN, महाराष्ट्र | 822 l wing ; country park phase iii ; opp tata steel ; dattapada road ; borivali east ; borivlai east ; mumbai suburban ; maharashtra | maharashtra (mapped_native) | 822 -> 822 | - | mumbai suburban ; borivlai east ; borivali east | - | high |
| S2-407865980 (train) | #136, VASUNDHARA COLONY, TONK ROAD, JAIPUR, राजस्थान | 136 ; vasundhara colony ; tonk road ; jaipur ; rajasthan | rajasthan (mapped_native) | 136 -> 136 | - | jaipur ; vasundhara colony | - | high |
| S2-605506004 (test) | Maharashtra, KOLHAPUR, MUMBAI, HN 61 MANIK CHAMBERS OFFICE 24 SYKES EXTN RAJARAMPURI | maharashtra ; kolhapur ; mumbai ; manik chambers office 24 sykes extn rajarampuri | maharashtra (exact) | 61 -> 61 (hn) ; 24 -> 24 (chambers office) | - | kolhapur ; mumbai | hn 61 | high |
| S2-737348946 (test) | SECOND FLOOR PLOT NO.19, P.K.SALAI, KOVILPATHU, KARAIKAL, Tamil Nadu | second floor plot 19 ; p k salai ; kovilpathu ; karaikal ; tamil nadu | tamil nadu (exact) | 19 -> 19 (plot no) | - | karaikal ; kovilpathu ; p k salai | - | high |
| S2-599206305 (test) | Tamil Nadu, VANDTLUO TO WALAJASALAI, VANJUVANCHERRY PADAPPAI, SRIPERUMBUDUR | tamil nadu ; vandtluo to walajasalai ; vanjuvancherry padappai ; sriperumbudur | tamil nadu (exact) | - | - | vandtluo to walajasalai ; vanjuvancherry padappai ; sriperumbudur | - | medium |
| S2-181117267 (train) | NO. 382 A-6, MUMBAI, Maharashtra | 382 a 6 ; mumbai ; maharashtra | maharashtra (exact) | 382 -> 382 (no) ; A-6 -> a6 (no 382) | - | mumbai | - | high |
| S2-511563696 (train) | INDUSTRIAL PLOT NO 401-A GROUND FLOOR FIRST FLOOR KENDRA -01 ECOTECH-III, GREATER NOIDA, Uttar Pradesh | industrial plot 401 a ground floor first floor kendra 1 ecotech iii ; greater noida ; uttar pradesh | uttar pradesh (exact) | 401 -> 401 (plot no) ; 01 -> 1 (floor kendra) | - | greater noida | - | high |
| S2-260913132 (test) | 1027, MUKHARJI NAGAR, NEW DELHI, Delhi | 1027 ; mukharji nagar ; new delhi ; delhi | delhi (exact) | 1027 -> 1027 | - | new delhi ; mukharji nagar | - | high |
| S2-104405169 (test) | E 26, GREATER KAILASH PART 1 NEW DELHI, DELHI, DELHI, दिल्ली | e 26 ; greater kailash part 1 new delhi ; delhi ; delhi ; delhi | delhi (exact) | E 26 -> e26 ; 1 -> 1 (kailash part) | - | - | - | high |
| S2-212927017 (train) | DIVYAM COMPLEX, GROUND F, SHOP NO. D/05, JAMNAGAR, JAMNAGAR, Gujarat | divyam complex ; ground f ; shop no d 5 ; jamnagar ; jamnagar ; gujarat | gujarat (exact) | 05 -> 5 (no d) | - | jamnagar ; ground f ; divyam complex | - | high |
| S2-187537458 (test) | Karnataka, A C-401, NCC URBAN ASTER PARK NEAR MOTHER DAIRY YELAHANKA NEW TOWN, BENGALURU | karnataka ; a c 401 ; ncc urban aster park near mother dairy yelahanka new town ; bengaluru | karnataka (exact) | C-401 -> c401 (a) | - | bengaluru | - | high |
| S2-54077938 (test) | FLAT NO 2 BUILDING NO 8 SNO 48, AMBA NAGARI VISHRANTWADI, PUNE CITY, Maharashtra | flat 2 building 8 sno 48 ; amba nagari vishrantwadi ; pune city ; maharashtra | maharashtra (exact) | 2 -> 2 (flat no) ; 8 -> 8 (building no) ; 48 -> 48 (8 sno) | - | pune city ; amba nagari vishrantwadi | - | high |
| S2-555160972 (test) | E 709, KALPATARU GRANDEUR, 27 YASHWANT NIWAS ROAD, INDORE, मध्य प्रदेश | e 709 ; kalpataru grandeur ; 27 yashwant niwas road ; indore ; madhya pradesh | madhya pradesh (mapped_native) | E 709 -> e709 ; 27 -> 27 | - | indore ; kalpataru grandeur | - | high |
| S2-774352922 (test) | NO 605 , D WING, S N 18, 19, GANESH NABHANGAN VADGAON DHAYARI, PUNE, महाराष्ट्र | 605 ; d wing ; s n 18 ; 19 ; ganesh nabhangan vadgaon dhayari ; pune ; maharashtra | maharashtra (mapped_native) | 605 -> 605 (no) ; N 18 -> n18 (s) ; 19 -> 19 | - | pune ; ganesh nabhangan vadgaon dhayari ; d wing | - | high |
| S2-598204091 (test) | AT POST KHONDAMALI, NANDURBAR, महाराष्ट्र | at post khondamali ; nandurbar ; maharashtra | maharashtra (mapped_native) | - | - | nandurbar ; at post khondamali | - | medium |
| S2-346805057 (test) | 7 , MAYUR SHRISHTI HEIGHTS, SNO.42/2/9, RAMNAGAR, RAHATANI, PUNE, महाराष्ट्र | 7 ; mayur shrishti heights ; sno 42 2 9 ; ramnagar ; rahatani ; pune ; maharashtra | maharashtra (mapped_native) | 7 -> 7 ; 42/2/9 -> 42/2/9 (sno) | - | pune ; rahatani ; ramnagar | - | high |
| S2-531471486 (train) | 11TH., FF-1117-1120-1121-1122-1122A, ELN MARCADO, DELHI JAIPUR, EXPRESSWAY, KUNDAN REFINERY PVT. LTD, SECTOR 80, NARSINGHPUR, Haryana | 11th ; ff 1117 1120 1121 1122 1122a ; eln marcado ; delhi jaipur ; expressway ; kundan refinery pvt ltd ; sector 80 ; narsinghpur ; haryana | haryana (exact) | FF-1117-1120-1121-1122-1122A -> ff1117-1120-1121-1122-1122a ; 80 -> 80 (sector) | - | narsinghpur ; kundan refinery pvt ltd ; expressway | - | high |
| S2-86412201 (test) | 1172, FIRST FLOOR, SIXTH AVENUE, ANNA NAGAR WEST, CHENNAI, Tamil Nadu | 1172 ; first floor ; sixth avenue ; anna nagar west ; chennai ; tamil nadu | tamil nadu (exact) | 1172 -> 1172 | - | chennai ; anna nagar west | - | high |
| S2-551506275 (test) | #149/157, FLAT NO-402, RASHMI RISE APARTMENT 80 FEET ROAD, BEML 4TH STAGE, RAJARAJESHW, ARI NAGAR, BANGALORE URBAN, BANGALORE, Karnataka | 149 157 ; flat 402 ; rashmi rise apartment 80 feet road ; beml 4th stage ; rajarajeshw ; ari nagar ; bangalore urban ; bangalore ; karnataka | karnataka (exact) | 149/157 -> 149/157 ; NO-402 -> no402 (flat) ; 80 -> 80 (rise apartment) | - | bangalore ; bangalore urban ; ari nagar | - | high |
| S2-203813600 (test) | NAWABGANJ, Uttar Pradesh, C/O GOPAL SUDARSHAN | nawabganj ; uttar pradesh ; c o gopal sudarshan | uttar pradesh (exact) | - | - | nawabganj ; c o gopal sudarshan | - | medium |
| S2-556954018 (test) | COMMERCIAL COMPLEX, HAPPY GOLDMINE SHOPPERS, UG- G-107, SURAT, CHORASI, ગુજરાત | commercial complex ; happy goldmine shoppers ; ug g 107 ; surat ; chorasi ; gujarat | gujarat (mapped_native) | G-107 -> g107 (ug) | - | chorasi ; surat ; happy goldmine shoppers | - | high |
| S2-330550901 (test) | 1413, VIKRAM TOWER RAJENDRA PLACE, NEW DELHI, Delhi | 1413 ; vikram tower rajendra place ; new delhi ; delhi | delhi (exact) | 1413 -> 1413 | - | new delhi | - | high |
| S2-210765685 (train) | FLAT NO.00304 , ABBLOCK, SAMSKRUTHI KALLM HOMES OPP: GUNTUR MEDICAL HOSTEL, AMARAVATHI R, OAD, GUNTUR, Andhra Pradesh | flat 304 ; abblock ; samskruthi kallm homes opp guntur medical hostel ; amaravathi r ; oad ; guntur ; andhra pradesh | andhra pradesh (exact) | 00304 -> 304 (flat no) | 00304 | guntur ; oad ; amaravathi r | - | high |
## India - source 3

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S3-670953420 (test) | Sr. No D/36/1/1b Olympia Business House Phase1, Poona, Pune, MH | sr no d 36 1 1b olympia business house phase1 ; poona ; pune ; maharashtra | maharashtra (alias) | 36/1/1b -> 36/1/1b (no d) | - | pune ; poona | - | high |
| S3-879403140 (train) | #563/564, Bangalore North, Bangalore, KA | 563 564 ; bangalore north ; bangalore ; karnataka | karnataka (alias) | 563/564 -> 563/564 | - | bangalore ; bangalore north | - | high |
| S3-990098891 (train) | Sachin Palsana Highway, Vadodara Region, Block No #26 Pardi Kande, GJ, Surat | sachin palsana highway ; block 26 pardi kande ; gujarat ; surat | gujarat (alias) | 26 -> 26 (block no) | - | surat | vadodara region | high |
| S3-309564187 (train) | House No. 160/7, Ground Floor, Mochi Bagh Village, Nanak Pura, Delhi-1, Delhi, South West Delhi, DL | house 160 7 ; ground floor ; mochi bagh village ; nanak pura ; delhi 1 ; delhi ; south west delhi ; delhi | delhi (exact) | 160/7 -> 160/7 (house no) ; 1 -> 1 (delhi) | - | south west delhi ; nanak pura ; mochi bagh village | - | high |
| S3-780830950 (train) | 1St Floor, Suvija Tower, Ernakulam, KL, Building No. 37/1134, Kanayannur | 1st floor ; suvija tower ; ernakulam ; kerala ; building 37 1134 ; kanayannur | kerala (alias) | 37/1134 -> 37/1134 (building no) | - | ernakulam ; suvija tower ; kanayannur | - | high |
| S3-889120181 (train) | Door No 311 Parishram Opp Cross Wardsmithakhali Six Roads, ગુજરાત, Ahmedabad | door 311 parishram opp cross wardsmithakhali six roads ; gujarat ; ahmedabad | gujarat (mapped_native) | 311 -> 311 (door no) | - | ahmedabad | - | high |
| S3-198200774 (test) | Bangalore, KA, 2Nd Cross, 9Th Main J.p.nagar 4Th Phase, Dollars Colony, Bangalore, #330/3 | bangalore ; karnataka ; 2nd cross ; 9th main j p nagar 4th phase ; dollars colony ; bangalore ; 330 3 | karnataka (alias) | 330/3 -> 330/3 | - | bangalore ; dollars colony | - | high |
| S3-738049485 (test) | Shop No 13-22, Fourth Floor, Satellite Complex, Koppikar Road, Hubli, Dharwad, Dharwar, Karnataka | shop 13 22 ; fourth floor ; satellite complex ; koppikar road ; hubli ; dharwad ; dharwar ; karnataka | karnataka (exact) | 13-22 -> 13-22 (shop no) | - | dharwar ; dharwad ; hubli | - | high |
| S3-158697505 (train) | B3/151, Veerabhadreshwara, Mallandur Road, Uppali, Chikmagalur Near Banu Prakash Sch, Ool, Chikmagalur, Chikmagalur, Chikamaglur, KA | 151 ; veerabhadreshwara ; mallandur road ; uppali ; chikmagalur near banu prakash sch ; ool ; chikmagalur ; chikmagalur ; chikamaglur ; karnataka | karnataka (alias) | B3/151 -> b3/151 | - | chikamaglur ; chikmagalur ; ool | b3 | high |
| S3-478685718 (test) | 101, Ground Floor, Asha Complex Mathiyadih, Opposite-petrol Pump, Dhaka Rd, Motihari, East Champaran, BR | 101 ; ground floor ; asha complex mathiyadih ; opposite petrol pump ; dhaka rd ; motihari ; east champaran ; bihar | bihar (alias) | 101 -> 101 | - | east champaran ; motihari ; dhaka rd | - | high |
| S3-287653539 (test) | 19 Veer Savarkar Block Shakarpur, Delhi, East Delhi, Delhi | 19 veer savarkar block shakarpur ; delhi ; east delhi ; delhi | delhi (exact) | 19 -> 19 | - | east delhi | - | high |
| S3-576107304 (test) | No 18, 9Th Cross, Chinnappa Garden, Jayamahal, Bangalore, KA | 18 ; 9th cross ; chinnappa garden ; jayamahal ; bangalore ; karnataka | karnataka (alias) | 18 -> 18 (no) | - | bangalore ; jayamahal ; chinnappa garden | - | high |
| S3-27930696 (test) | Mahendra Singh, Ghaziabad, UP | mahendra singh ; ghaziabad ; uttar pradesh | uttar pradesh (alias) | - | - | ghaziabad ; mahendra singh | - | medium |
| S3-333883774 (train) | C-46, Sector-39, Hapur (PANCHSHEEL Nagar), <NULL>, UP | c 46 ; sector 39 ; hapur panchsheel nagar ; uttar pradesh | uttar pradesh (alias) | C-46 -> c46 ; 39 -> 39 (sector) | - | hapur panchsheel nagar | - / nulls 1 | high |
| S3-860556400 (test) | G7, 98, Guru Sampada Apartment, Chikitasak Nagar, Indore, MP | g7 ; 98 ; guru sampada apartment ; chikitasak nagar ; indore ; madhya pradesh | madhya pradesh (alias) | G7 -> g7 ; 98 -> 98 | - | indore ; chikitasak nagar | - | high |
| S3-514108392 (test) | D-#235 Ground Floor Baljeet Nagar, DL, New Delhi, Central Delhi | d 235 ground floor baljeet nagar ; delhi ; new delhi ; central delhi | delhi (alias) | 235 -> 235 (d) | - | new delhi ; central delhi | - | high |
| S3-324480967 (train) | J-63, Basement, Saket, Malviya Nagar, New Delhi, South Delhi, DL | j 63 ; basement ; saket ; malviya nagar ; new delhi ; south delhi ; delhi | delhi (alias) | J-63 -> j63 | - | south delhi ; new delhi ; malviya nagar | - | high |
| S3-471504100 (train) | 204, West Delhi, New Delhi, DL | 204 ; west delhi ; new delhi ; delhi | delhi (alias) | 204 -> 204 | - | new delhi ; west delhi | - | high |
| S3-849402250 (train) | ##1003 Manju Apartment10th Floor Nepean Sea Road, Mumbai, MH | 1003 manju apartment10th floor nepean sea road ; mumbai ; maharashtra | maharashtra (alias) | 1003 -> 1003 | - | mumbai | - | high |
| S3-444099901 (test) | Door No 3 J Block Gr.floorbhangwadi Shopping Centre Kalbadevi Road, Mumbai, MH | door 3 j block gr floorbhangwadi shopping centre kalbadevi road ; mumbai ; maharashtra | maharashtra (alias) | 3 -> 3 (door no) | - | mumbai | - | high |
| S3-816624610 (test) | Bengaluru, C 301, ಕರ್ನಾಟಕ, Esteem Royale, S T Bed Road Opposite Nirguna Mandir, Koramangala 1St, Block | bengaluru ; c 301 ; karnataka ; esteem royale ; s t bed road opposite nirguna mandir ; koramangala 1st ; block | karnataka (mapped_native) | C 301 -> c301 | - | esteem royale ; bengaluru | - | high |
| S3-353239001 (train) | Block-4, Gsc Sector-29, Doro No 53, Gautam Buddha Nagar, UP, Noida | block 4 ; gsc sector 29 ; doro 53 ; gautam buddha nagar ; uttar pradesh ; noida | uttar pradesh (alias) | 4 -> 4 (block) ; 29 -> 29 (gsc sector) ; 53 -> 53 (doro no) | - | gautam buddha nagar ; noida | - | high |
| S3-953869264 (train) | 5Th Lane Teachers Colony Nunna Vikas College Street, Vijayawada, Krishna, AP | 5th lane teachers colony nunna vikas college street ; vijayawada ; krishna ; andhra pradesh | andhra pradesh (alias) | - | - | krishna ; vijayawada | - | medium |
| S3-673979511 (train) | H.no 15, Iiird Street, Tngo Colony Adambakkam, Chennai, TN | h 15 ; iiird street ; tngo colony adambakkam ; chennai ; tamil nadu | tamil nadu (alias) | 15 -> 15 (h no) | - | chennai ; tngo colony adambakkam | - | high |
| S3-273789205 (test) | 21 Amrlk Singh Road, Bathinda, PB | 21 amrlk singh road ; bathinda ; punjab | punjab (alias) | 21 -> 21 | - | bathinda | - | high |
| S3-55150575 (test) | 32-Akshat Estate, Ahmedabad, GJ | 32 akshat estate ; ahmedabad ; gujarat | gujarat (alias) | 32 -> 32 | - | ahmedabad | - | high |
| S3-964510882 (train) | Off No.201 Pt No.4 Sec 18, MH, Thane | off 201 pt 4 sec 18 ; maharashtra ; thane | maharashtra (alias) | 201 -> 201 (off no) ; 4 -> 4 (pt no) ; 18 -> 18 (4 sec) | - | thane | - | high |
| S3-110938804 (test) | Lucknow, 1193, Uttar Pradesh, Lucknow, Front Of Goverdhan, Enclave, Near Sector-20 | lucknow ; 1193 ; uttar pradesh ; lucknow ; front of goverdhan ; enclave ; near sector 20 | uttar pradesh (exact) | 1193 -> 1193 ; 20 -> 20 (near sector) | - | lucknow ; front of goverdhan ; enclave | - | high |
| S3-178115448 (train) | Plot 11 House No.15, Jalandhar - I, Jalandhar, PB | plot 11 house 15 ; jalandhar i ; jalandhar ; punjab | punjab (alias) | 11 -> 11 (plot) ; 15 -> 15 (house no) | - | jalandhar ; jalandhar i | - | high |
| S3-599922343 (train) | Block E-916 1A, Mumbai, महाराष्ट्र | block e 916 1a ; mumbai ; maharashtra | maharashtra (mapped_native) | E-916 -> e916 (block) ; 1A -> 1a (e 916) | - | mumbai | - | high |
## US - source 1

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S1-385531649 (train) | TN, Byrdstown, 1013 Eastridge Drive | tennessee ; byrdstown ; 1013 eastridge drive | tennessee (alias) | 1013 -> 1013 | - | byrdstown | - | high |
| S1-555692956 (test) | 2620 Berwyn Road, Columbus, OH | 2620 berwyn road ; columbus ; ohio | ohio (alias) | 2620 -> 2620 | - | columbus | - | high |
| S1-105160077 (train) | 4067 Merrick Street, Houston, TX | 4067 merrick street ; houston ; texas | texas (alias) | 4067 -> 4067 | - | houston | - | high |
| S1-866669260 (train) | 5267 Crown Hill Drive, Cedar Hill, MO | 5267 crown hill drive ; cedar hill ; missouri | missouri (alias) | 5267 -> 5267 | - | cedar hill | - | high |
| S1-761597376 (test) | 26 Lake Road, Trumbull, CT | 26 lake road ; trumbull ; connecticut | connecticut (alias) | 26 -> 26 | - | trumbull | - | high |
| S1-243724259 (train) | 1715 Poplar Street, Kenova, WV | 1715 poplar street ; kenova ; west virginia | west virginia (alias) | 1715 -> 1715 | - | kenova | - | high |
| S1-126153442 (test) | 148 Horseshoe Road, Conesville, NY | 148 horseshoe road ; conesville ; new york | new york (alias) | 148 -> 148 | - | conesville | - | high |
| S1-874709722 (train) | 324 North Street, Monroe Township, PA | 324 north street ; monroe township ; pennsylvania | pennsylvania (alias) | 324 -> 324 | - | monroe township | - | high |
| S1-265953116 (train) | 1665 Park Avenue, IN, Indianapolis | 1665 park avenue ; indiana ; indianapolis | indiana (alias) | 1665 -> 1665 | - | indianapolis | - | high |
| S1-342963431 (train) | KS, Baxter Springs, 602 18th Street | kansas ; baxter springs ; 602 18th street | kansas (alias) | 602 -> 602 | - | baxter springs | - | high |
| S1-103476121 (train) | 2391 River Oaks Drive, Columbus, OH | 2391 river oaks drive ; columbus ; ohio | ohio (alias) | 2391 -> 2391 | - | columbus | - | high |
| S1-982814151 (test) | 2641 Selbourne Drive, Gastonia, NC | 2641 selbourne drive ; gastonia ; north carolina | north carolina (alias) | 2641 -> 2641 | - | gastonia | - | high |
| S1-326544762 (train) | 714 Thatcher Street, Texarkana, AR | 714 thatcher street ; texarkana ; arkansas | arkansas (alias) | 714 -> 714 | - | texarkana | - | high |
| S1-907175984 (train) | New York, NY, 46 Claremont Avenue | new york ; new york ; 46 claremont avenue | new york (exact) | 46 -> 46 | - | - | - | high |
| S1-171883990 (train) | 8817 Michaw Court, Charlotte, NC | 8817 michaw court ; charlotte ; north carolina | north carolina (alias) | 8817 -> 8817 | - | charlotte | - | high |
| S1-608056976 (train) | 14228 Crane Street, Andover, MN | 14228 crane street ; andover ; minnesota | minnesota (alias) | 14228 -> 14228 | 14228 | andover | - | high |
| S1-91439917 (train) | 219 Anthoni Avenue, Wheeling, WV | 219 anthoni avenue ; wheeling ; west virginia | west virginia (alias) | 219 -> 219 | - | wheeling | - | high |
| S1-349297186 (test) | Unit C, Wareham, 21 Linwood Avenue, MA | unit c ; wareham ; 21 linwood avenue ; massachusetts | massachusetts (alias) | 21 -> 21 | - | wareham | - | high |
| S1-156567762 (test) | 102 Paschal Street, Troup, TX | 102 paschal street ; troup ; texas | texas (alias) | 102 -> 102 | - | troup | - | high |
| S1-218031887 (test) | Manlius, NY, 257 Oarlock Circle | manlius ; new york ; 257 oarlock circle | new york (alias) | 257 -> 257 | - | manlius | - | high |
| S1-116674585 (train) | 6014 Marzilli Street, Canton, OH | 6014 marzilli street ; canton ; ohio | ohio (alias) | 6014 -> 6014 | - | canton | - | high |
| S1-947765325 (test) | 735 Burnham Drive, Unit 1, University Park, IL | 735 burnham drive ; unit 1 ; university park ; illinois | illinois (alias) | 735 -> 735 ; 1 -> 1 (unit) | - | university park | - | high |
| S1-686835511 (train) | 3188 Tennyson Place, Independence, KY | 3188 tennyson place ; independence ; kentucky | kentucky (alias) | 3188 -> 3188 | - | independence | - | high |
| S1-938545059 (test) | 840 Ridge Road, Mount Airy, MD | 840 ridge road ; mount airy ; maryland | maryland (alias) | 840 -> 840 | - | mount airy | - | high |
| S1-678822664 (test) | 35 Barberry Court, Milford, CT | 35 barberry court ; milford ; connecticut | connecticut (alias) | 35 -> 35 | - | milford | - | high |
| S1-798751455 (test) | 805 337, Gravel Switch, KY | 805 337 ; gravel switch ; kentucky | kentucky (alias) | 805 -> 805 ; 337 -> 337 (805) | - | gravel switch | - | high |
| S1-758850533 (train) | 322 Lane Avenue, Columbus, OH | 322 lane avenue ; columbus ; ohio | ohio (alias) | 322 -> 322 | - | columbus | - | high |
| S1-266227506 (test) | 2336 Richey Boulevard, Tucson, AZ | 2336 richey boulevard ; tucson ; arizona | arizona (alias) | 2336 -> 2336 | - | tucson | - | high |
| S1-314593809 (test) | 4000 Green River Road, Evansville, IN | 4000 green river road ; evansville ; indiana | indiana (alias) | 4000 -> 4000 | - | evansville | - | high |
| S1-366098900 (train) | Moody, 330 County Road 339, TX | moody ; 330 county road 339 ; texas | texas (alias) | 330 -> 330 ; 339 -> 339 (county road) | - | moody | - | high |
## US - source 2

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S2-98554258 (train) | 861 TOBERMORY ROAD, FAYETTEVILLE, NC | 861 tobermory road ; fayetteville ; north carolina | north carolina (alias) | 861 -> 861 | - | fayetteville | - | high |
| S2-402670848 (test) | 1621 OAKWOOD AVE, CITY OF BELOIT, WI | 1621 oakwood avenue ; city of beloit ; wisconsin | wisconsin (alias) | 1621 -> 1621 | - | city of beloit | - | high |
| S2-433746422 (test) | 7776 BAY OKS DR, BROWNWOOD, TX | 7776 bay oks drive ; brownwood ; texas | texas (alias) | 7776 -> 7776 | - | brownwood | - | high |
| S2-815634522 (train) | 2818 WOODSDALE BLVD, LINCOLN, NE | 2818 woodsdale boulevard ; lincoln ; nebraska | nebraska (alias) | 2818 -> 2818 | - | lincoln | - | high |
| S2-266963756 (train) | 2 SWEETBRIAR DRIVE, SMITHTOWN, NY | 2 sweetbriar drive ; smithtown ; new york | new york (alias) | 2 -> 2 | - | smithtown | - | high |
| S2-934573349 (train) | 115 WIGWAM LN, STRATFORD, CT | 115 wigwam lane ; stratford ; connecticut | connecticut (alias) | 115 -> 115 | - | stratford | - | high |
| S2-117241198 (test) | VESTAVIA HILLS, 002034 Montreat Cir, AL | vestavia hills ; 2034 montreat circle ; alabama | alabama (alias) | 002034 -> 2034 | 002034 | vestavia hills | - | high |
| S2-747041330 (train) | 130A ROSEWOOD DRIVE, JASPER, TX | 130a rosewood drive ; jasper ; texas | texas (alias) | 130A -> 130a | - | jasper | - | high |
| S2-440759161 (test) | 14374 RUSSELL ST, MILTON, DE | 14374 russell street ; milton ; delaware | delaware (alias) | 14374 -> 14374 | 14374 | milton | - | high |
| S2-177201547 (test) | 10414 Higgins Switch Road, LITTLLE ROCK, AR | 10414 higgins switch road ; littlle rock ; arkansas | arkansas (alias) | 10414 -> 10414 | 10414 | littlle rock | - | high |
| S2-529430972 (test) | 5716 61st Ave, OMAHHA, NE | 5716 61st avenue ; omahha ; nebraska | nebraska (alias) | 5716 -> 5716 | - | omahha | - | high |
| S2-576550256 (test) | 716-718 NEBRASKA SAINT, PINE BLUFF, AR | 716 718 nebraska saint ; pine bluff ; arkansas | arkansas (alias) | 716-718 -> 716-718 | - | pine bluff | - | high |
| S2-230695063 (train) | 10152 RACETRACK RD, WORCESTER COUNTY, MD | 10152 racetrack road ; worcester county ; maryland | maryland (alias) | 10152 -> 10152 | 10152 | worcester county | - | high |
| S2-956565968 (train) | 978 FREMONT AVENUE, PANESVILLE CITY, OH | 978 fremont avenue ; panesville city ; ohio | ohio (alias) | 978 -> 978 | - | panesville city | - | high |
| S2-259997746 (train) | 248 ST CHRISTOPHER LN, COLUMBUS, OH | 248 st christopher lane ; columbus ; ohio | ohio (alias) | 248 -> 248 | - | columbus | - | high |
| S2-719603630 (train) | 18450 SUNDANCER LANE, AMARILLO, TX | 18450 sundancer lane ; amarillo ; texas | texas (alias) | 18450 -> 18450 | 18450 | amarillo | - | high |
| S2-978174320 (train) | 1316 GILKEY RAOD, BURLINGTON, WA | 1316 gilkey raod ; burlington ; washington | washington (alias) | 1316 -> 1316 | - | burlington | - | high |
| S2-22615836 (test) | 14331 1/2 MANCHESTER ROAD, BALLWIIN, MO | 14331 1 2 manchester road ; ballwiin ; missouri | missouri (alias) | 14331 -> 14331 ; 1/2 -> 1/2 (14331) | 14331 | ballwiin | - | high |
| S2-625853344 (train) | 1131  MAJESTIC WOODS DRIVE, GRAND ISLAND, NY | 1131 majestic woods drive ; grand island ; new york | new york (alias) | 1131 -> 1131 | - | grand island | - | high |
| S2-995367107 (train) | 111 CASALINDA CIRCLE, HOT SPRINGS NATIONAL PARK, AR | 111 casalinda circle ; hot springs national park ; arkansas | arkansas (alias) | 111 -> 111 | - | hot springs national park | - | high |
| S2-584661811 (test) | 646 1603, GRAND SALINE, TX | 646 1603 ; grand saline ; texas | texas (alias) | 646 -> 646 ; 1603 -> 1603 (646) | - | grand saline | - | high |
| S2-2345511 (train) | 4874 WHISPERING BELSL LN, QUEEN CREEK, AZ | 4874 whispering belsl lane ; queen creek ; arizona | arizona (alias) | 4874 -> 4874 | - | queen creek | - | high |
| S2-593243418 (train) | 2313. 13D AVE, RUSO, ND | 2313 13d avenue ; ruso ; north dakota | north dakota (alias) | 2313 -> 2313 ; 13D -> 13d (2313) | - | ruso | - | high |
| S2-362051411 (test) | ST FRANCIS 611 RD, HUGHES, AR | st francis 611 road ; hughes ; arkansas | arkansas (alias) | 611 -> 611 (st francis) | - | hughes | - | high |
| S2-517405135 (train) | 1632 SHERBURNE AVE, SAINTP AUL, MN | 1632 sherburne avenue ; saintp aul ; minnesota | minnesota (alias) | 1632 -> 1632 | - | saintp aul | - | high |
| S2-239852623 (train) | 14 MACARTHUR LANE, MARSHFIELD, MA | 14 macarthur lane ; marshfield ; massachusetts | massachusetts (alias) | 14 -> 14 | - | marshfield | - | high |
| S2-46612786 (test) | 05887 BARREN RIVER RD, BOWLING GREEN, KY | 5887 barren river road ; bowling green ; kentucky | kentucky (alias) | 05887 -> 5887 | 05887 | bowling green | - | high |
| S2-858553635 (train) | 6 CASTLE LN, BROOKHAVEN, NY | 6 castle lane ; brookhaven ; new york | new york (alias) | 6 -> 6 | - | brookhaven | - | high |
| S2-360971884 (test) | 1201 DARLINGTON DR, LOWELL, NC | 1201 darlington drive ; lowell ; north carolina | north carolina (alias) | 1201 -> 1201 | - | lowell | - | high |
| S2-877765754 (test) | 50- BEVERLY ROAD, WETHERSFIELD, CT | 50 beverly road ; wethersfield ; connecticut | connecticut (alias) | 50 -> 50 | - | wethersfield | - | high |
## US - source 3

| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |
|---|---|---|---|---|---|---|---|---|
| S3-709820693 (train) | 129 North Main Street, Flatonia, Texas | 129 north main street ; flatonia ; texas | texas (exact) | 129 -> 129 | - | flatonia | - | high |
| S3-151861836 (train) | 247 Meadow Road, RCKY HILL, Connecticut | 247 meadow road ; rcky hill ; connecticut | connecticut (exact) | 247 -> 247 | - | rcky hill | - | high |
| S3-106883724 (train) | Antoine Court, Unit Unit 2, Huntington CDP, New York | antoine court ; unit unit 2 ; huntington ; new york | new york (exact) | 2 -> 2 (unit unit) | - | huntington | cdp | high |
| S3-870003881 (train) | 702 Fifth, TELL CITY CITY, Indiana | 702 fifth ; tell city city ; indiana | indiana (exact) | 702 -> 702 | - | tell city city | - | high |
| S3-199189626 (test) | 2950-2954 1050, Wyoming, Illinois | 2950 2954 1050 ; wyoming ; illinois | - (conflict) | 2950-2954 -> 2950-2954 ; 1050 -> 1050 (2950 2954) | - | - | - | medium |
| S3-117272218 (test) | 786 Glencoe Ave, Simi Valley, California | 786 glencoe avenue ; simi valley ; california | california (exact) | 786 -> 786 | - | simi valley | - | high |
| S3-172461589 (test) | 3844. 124th Street, Alsip, Illinois | 3844 124th street ; alsip ; illinois | illinois (exact) | 3844 -> 3844 | - | alsip | - | high |
| S3-922705319 (train) | 122 Cooper Ave, Yorkville, New York | 122 cooper avenue ; yorkville ; new york | new york (exact) | 122 -> 122 | - | yorkville | - | high |
| S3-374056130 (test) | Eugene, 001608 Danebo Ave, Oregon | eugene ; 1608 danebo avenue ; oregon | oregon (exact) | 001608 -> 1608 | 001608 | eugene | - | high |
| S3-854070293 (test) | 6114d Green Cap Pl, Fairfax County, Virginia | 6114d green cap place ; fairfax county ; virginia | virginia (exact) | 6114d -> 6114d | - | fairfax county | - | high |
| S3-566561662 (test) | 583 Hunt Ave, Hydro, Oklahoma | 583 hunt avenue ; hydro ; oklahoma | oklahoma (exact) | 583 -> 583 | - | hydro | - | high |
| S3-871210198 (train) | Somerville, 136 Curtis Street, Massachusetts | somerville ; 136 curtis street ; massachusetts | massachusetts (exact) | 136 -> 136 | - | somerville | - | high |
| S3-266151234 (test) | 717 Ocean View Dr, Port Hueneme, California | 717 ocean view drive ; port hueneme ; california | california (exact) | 717 -> 717 | - | port hueneme | - | high |
| S3-496597060 (test) | Hopkins, Minnesota, 1306 Oxford St | hopkins ; minnesota ; 1306 oxford street | minnesota (exact) | 1306 -> 1306 | - | hopkins | - | high |
| S3-10216688 (train) | ##50 Mckinley St, Cookeville, Tennessee | 50 mckinley street ; cookeville ; tennessee | tennessee (exact) | 50 -> 50 | - | cookeville | - | high |
| S3-70170061 (test) | Missouri, Galena, 76 Fox Squirrel Rd | missouri ; galena ; 76 fox squirrel road | missouri (exact) | 76 -> 76 | - | galena | - | high |
| S3-114941136 (test) | 1819 1/2 Oneida St, PO Box 1269, Appleton, Wisconsin | 1819 1 2 oneida street ; appleton ; wisconsin | wisconsin (exact) | 1819 -> 1819 ; 1/2 -> 1/2 (1819) ; 1269 -> 1269 (po box) | - | appleton | po box 1269 | high |
| S3-551861014 (train) | 1698 Hewitt Ave, Troutdale CITY, Oregon | 1698 hewitt avenue ; troutdale city ; oregon | oregon (exact) | 1698 -> 1698 | - | troutdale city | - | high |
| S3-574243143 (test) | 1836 Page Rd, Durham, North Carolina | 1836 page road ; durham ; north carolina | north carolina (exact) | 1836 -> 1836 | - | durham | - | high |
| S3-529923180 (test) | Beeulah, 695 Chaffee Row, North Dakota | beeulah ; 695 chaffee row ; north dakota | north dakota (exact) | 695 -> 695 | - | beeulah | - | high |
| S3-65122627 (test) | 588-B Cabrera Ave, SAN Bernaardino, California | 588 b cabrera avenue ; san bernaardino ; california | california (exact) | 588 -> 588 | - | san bernaardino | - | high |
| S3-944291100 (test) | 75- Pittsburgh Loop, Mentmore, New Mexico | 75 pittsburgh loop ; mentmore ; new mexico | new mexico (exact) | 75 -> 75 | - | mentmore | - | high |
| S3-694662612 (test) | 6490 Walnut Point Way, Hamilton, Ohio | 6490 walnut point way ; hamilton ; ohio | ohio (exact) | 6490 -> 6490 | - | hamilton | - | high |
| S3-34806924 (train) | 9154 Whispering Pine Drive, Tucson, Arizona | 9154 whispering pine drive ; tucson ; arizona | arizona (exact) | 9154 -> 9154 | - | tucson | - | high |
| S3-776457460 (test) | 1604-A Coleman St, Nacogdoches CITY, Texas | 1604 a coleman street ; nacogdoches city ; texas | texas (exact) | 1604 -> 1604 | - | nacogdoches city | - | high |
| S3-260771846 (train) | 1 Maid Marion Street, Massachusetts, Oxford | 1 maid marion street ; massachusetts ; oxford | massachusetts (exact) | 1 -> 1 | - | oxford | - | high |
| S3-489032490 (train) | 121 River Bend Dr, Georgetown, Texas | 121 river bend drive ; georgetown ; texas | texas (exact) | 121 -> 121 | - | georgetown | - | high |
| S3-959048117 (train) | 2807 Dell Brooke Ave, Louisville, Kentucky | 2807 dell brooke avenue ; louisville ; kentucky | kentucky (exact) | 2807 -> 2807 | - | louisville | - | high |
| S3-331881775 (test) | 5002 Kings Highland Dr, # C308, Columbus, Ohio | 5002 kings highland drive ; c308 ; columbus ; ohio | ohio (exact) | 5002 -> 5002 ; C308 -> c308 | - | columbus | - | high |
| S3-586070539 (test) | Louisiana, 24172 Plank Rd, Zachary | louisiana ; 24172 plank road ; zachary | louisiana (exact) | 24172 -> 24172 | 24172 | zachary | - | high |

## Review notes

Reviewed by A on 26 September 2026: all 270 rows of this file (30 per country x source, from the final `feat_v2_0` table) plus an 8-per-group sample of an earlier build, which is where the first three findings below came from.

**Correct in every reviewed row:** state mapping (2-letter codes, English names, native scripts, aliases `Orissa`/`Keralam`, France départements -> region), zero stripping (`002034` -> `2034`, `05887` -> `5887`), street-type expansion (`AVE`, `LN`, `BLVD`, France `R`/`IMP`/`RTE`), `Bis`/`1/2` number spans, removal of `CDP`, `PO BOX n`, `HN n`, `b3`, `<x> Region` and `NULL` segments (each reported in the "removed / nulls" column), and that no segment lost a digit.

**Found during review and fixed before the final build:**
1. `Plot No, 93` kept `no` while `Plot No 93` lost it (100 of 144,216 sampled India rows) -> label dropped across a comma (rule A-14).
2. India S2/S3 carry injected `HN <number>`, `B3`, `<place> Region` and `DIVREPORTINGCIRCLE` components that S1 never has -> rule A-12 (found by scanning the census for high-lift tokens; confirmed on true pairs: 0-3% of them occur in the S1 address).
3. `RALPH CT`, `HWY 64` were not expanded because `CT` is also the state code -> rule A-13 with `suffix_multi`.
4. The strict fixed-point check (canon of canon) failed for `B03` because zeros were stripped after the noise rules -> zeros are now stripped first.

**Known limits (documented, not fixed):**
- `NO119`, `KN078` (two letters, no hyphen) are not number spans, so the row can be `medium` although it contains a number (about 0.5% of India rows; natural variety, S1 has it too).
- `Wyoming, Illinois` (a US city named like a state) gives `conflict` and an empty state (0.64% of US rows). France has no region in 29.6% of rows (S2/S3 often drop it), so 28.3% of France rows are `medium`.
- City spelling variants and typos (`OMAHHA`, `LITTLLE ROCK`, `Bangalore`/`Bengaluru`, `Bombay`/`Mumbai`) are not merged: they are a similarity problem for B's fuzzy features, not a canonicalisation problem.
- S3 appends `CITY` to about 1.4 pp more US rows than S1 (`Troutdale CITY`); dropping it is a measured candidate for `feat_v2_1` (see "Things measured that did not help" in the decisions log).
- The number spans keep an injected number (`PO BOX 1269`, `HN 61`) with its context word, on purpose: B can discount by context.
