# Hygiene before/after examples

First four rows (by entity ID) that each repair changed, over all six files. The first string is the raw field, the second is `name_hyg` (a v1-style key) or `address_clean` (text view).

## address: `controls`

- S1-100454525: `'Jamdheeh Pandey Post Â\x80\x93 Labnapar, Basti, Uttar Pradesh'` -> `'Jamdheeh Pandey Post Labnapar, Basti, Uttar Pradesh'`
- S1-101401745: `'New Delhi, Delhi, Unit No \x1a 35, Jasola District Centre, Ground Floor, Omaxe Square, Plot No 14'` -> `'New Delhi, Delhi, Unit No 35, Jasola District Centre, Ground Floor, Omaxe Square, Plot No 14'`
- S1-103069906: `'401, Plot No. 7, The Youngâ\x80\x99S Cghs Sector 64, Faridabad, Haryana'` -> `'401, Plot No. 7, The Young S Cghs Sector 64, Faridabad, Haryana'`
- S1-103917324: `'Module No.1201, 12Th Floor, Ticel Biopark Limited, Phase Â\x80\x93Ii, No.5, Csir Campus Road, Tar, Amani, Chennai, Tamil Nadu'` -> `'Module No.1201, 12Th Floor, Ticel Biopark Limited, Phase Ii, No.5, Csir Campus Road, Tar, Amani, Chennai, Tamil Nadu'`

## address: `punct`

- S1-100551058: `'41 Place d’Armes, Calais, Hauts-de-France'` -> `"41 Place d'Armes, Calais, Hauts-de-France"`
- S1-100614060: `'9 bis Rue de l’Anjou, La Teste-de-Buch, Nouvelle-Aquitaine'` -> `"9 bis Rue de l'Anjou, La Teste-de-Buch, Nouvelle-Aquitaine"`
- S1-100663857: `'87 Rue Franchet d’Esperey, Dunkerque, Hauts-de-France'` -> `"87 Rue Franchet d'Esperey, Dunkerque, Hauts-de-France"`
- S1-101282236: `'760 Boulevard de l’Industrie, Nouvelle-Aquitaine, La Teste-de-Buch'` -> `"760 Boulevard de l'Industrie, Nouvelle-Aquitaine, La Teste-de-Buch"`

## address: `ws`

- S1-100208343: `'4104 130th Avenue E, Unit APARTMENT  412, Tulsa, OK'` -> `'4104 130th Avenue E, Unit APARTMENT 412, Tulsa, OK'`
- S1-100258519: `'Tulsa, OK, Unit APARTMENT  2018, 5210 Lewis Avenue'` -> `'Tulsa, OK, Unit APARTMENT 2018, 5210 Lewis Avenue'`
- S1-100454525: `'Jamdheeh Pandey Post Â\x80\x93 Labnapar, Basti, Uttar Pradesh'` -> `'Jamdheeh Pandey Post Labnapar, Basti, Uttar Pradesh'`
- S1-100473156: `'1741 Baltimore Avenue, Unit APARTMENT  15, Tulsa, OK'` -> `'1741 Baltimore Avenue, Unit APARTMENT 15, Tulsa, OK'`

## name: `controls`

- S1-34890563: `'D\x92accueil Ecole SARL'` -> `'d accueil ecole sarl'`
- S1-881107059: `'D\x92aide & Frères SARL'` -> `'d aide frères sarl'`
- S1-930893679: `'Medchal\x1aMalkajgiri Housekeeping Private Limited'` -> `'medchal malkajgiri housekeeping private limited'`
- S2-201694289: `'D\x92accueil École SARL'` -> `'d accueil école sarl'`

## name: `dotted`

- S1-100004153: `'Gonzalez, Aurelea, L.C.S.W., P.C.'` -> `'gonzalez aurelea lcsw pc'`
- S1-100016578: `'Capital All Institutions P.C.'` -> `'capital all institutions pc'`
- S1-100029574: `'Berget Toran, P.A., DDS PC'` -> `'berget toran pa dds pc'`
- S1-100047007: `'Pediatric Dental Care P.C.'` -> `'pediatric dental care pc'`

## name: `joiners`

- S2-100051010: `'ಸಿಟಿ ಎಂಟರ್\u200cಪ್ರೈಸಸ್'` -> `'ಸಿಟಿ ಎಂಟರ್ಪ್ರೈಸಸ್'`
- S2-100080376: `'ಏಸ್ ಕನ್\u200cಸ್ಟ್ರಕ್ಷನ್ಸ್ ಪ್ರೈವೇಟ್ ಲಿಮಿಟೆಡ್'` -> `'ಏಸ್ ಕನ್ಸ್ಟ್ರಕ್ಷನ್ಸ್ ಪ್ರೈವೇಟ್ ಲಿಮಿಟೆಡ್'`
- S2-100087372: `'ഇന്തോ ഹെൽത്ത്\u200cകെയർ പ്രൈവറ്റ് ലിമിറ്റഡ്'` -> `'ഇന്തോ ഹെൽത്ത്കെയർ പ്രൈവറ്റ് ലിമിറ്റഡ്'`
- S2-100119914: `'గ్రీన్ ఇన్\u200cఫ్రాస్ట్రక్చర్ ఎల్\u200cఎల్\u200cపీ'` -> `'గ్రీన్ ఇన్ఫ్రాస్ట్రక్చర్ ఎల్ఎల్పీ'`

## name: `ws`

- S2-100000037: `'PREMIER INC  PRODUCTS LEARNING'` -> `'premier inc products learning'`
- S2-100001819: `'VIJAYAWADA  AI LIMITED'` -> `'vijayawada ai limited'`
- S2-100002256: `'International Enterprises Trading Private  Limited'` -> `'international enterprises trading private limited'`
- S2-100003189: `'MARLO  PEREZ SERVICES'` -> `'marlo perez services'`
