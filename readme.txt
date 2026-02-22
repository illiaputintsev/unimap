Version 7.4 Produced 2025-08-04

National Student Survey

The National Student Survey was updated in 2025 following a major review and consultation. As a result, the survey questions and response scales have changed for NSS 2025. The updated survey asks students in the UK questions about a range of factors related to their academic experience, including the teaching on their course, assessment and feedback, and how well courses are organised. The 2025 survey also asked students about mental wellbeing services and, in England, about freedom of expression for the first time. New direct questions with item-specific response scales have been introduced to improve students’ understanding and to enhance the accuracy of results.

As the 2025 survey has been updated, it is not valid to either compare question responses or combine data from the NSS 2025 with those from previous years. Therefore, the NSS data displayed in the Discover Uni dataset is for two years, taken from students who were in their final year of their higher education course during the academic years 2023-2024 and 2024-2025.

For more information on the use of the data: https://www.officeforstudents.org.uk/advice-and-guidance/student-information-and-data/national-student-survey-nss/

Teaching and Excellence Framework (TEF)

From 11th October 2023, the TEF ratings for participating providers will be included in the Discover Uni dataset. The TEF is a national scheme run by the Office for Students (OfS) that aims to encourage higher education providers to improve and deliver excellence in the areas that students care about the most: teaching, learning and achieving positive outcomes from their studies.  The TEF does this by assessing and rating universities and colleges for excellence above a set of minimum requirements for quality and standards. Providers that take part in the TEF receive an overall rating as well as two underpinning ratings – one for the student experience and one for student outcomes. 

The Discover Uni .csv files have been included in this folder to enable users to load .csv versions of the kis.xml file entities into their databases for analysis.

The .csv file structure is based on that created for the Discover Uni output .xml file with some exceptions (see paragraph below). 

This documentation includes details of the parent entity, field description, field type, min/max occurrence, field length and additional notes.  Field information for the .csv lookup tables (ACCREDITATIONTABLE.csv, KISAIM.csv, LOCATION.csv, GOSECSAL.csv, LEO3SECSAL.csv and LEO5SECSAL.csv), plus the two additional .csv entities (UCASCOURSEID.csv and SBJ.csv (created to hold the COURSELOCATION UCASCOURSEID and KISCourse SBJ repeating fields)), can be found in the 'Discover Uni dataset file structure and description' 

https://www.hesa.ac.uk/collection/C25061/filestructure

The .csv file name, the entity name, the entity description, how to join to other files and additional notes, if applicable, are listed below:

ACCREDITATION.csv, 
Accreditation entity, 
Contains information about course accreditation, 
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

ACCREDITATIONTABLE.csv, 
Accreditation lookup table,
Contains the accrediting body text and accreditation url for each ACCTYPE,
Lookup table
(This lookup table may be linked to the ACCREDITATION entity using ACCTYPE)

COMMON.csv, 
Common job types entity, 
Contains information relating to common job types obtained by students taking the course, 
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE,
Linked to JOBLIST entity using PUBUKPRN, KISCOURSEID, KISMODE and COMSBJ,
(Note COMSBJ may contain nulls)

CONTINUATION.csv,
Continuation entity,
Contains continuation information for students on the course,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

COURSELOCATION.csv,
Course location entity,
Contains details of the KIS course location,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE
Linked to UCASCOURSEID entity using PUBUKPRN, KISCOURSEID, KISMODE and LOCID
(Note LOCID may contain nulls)

EMPLOYMENT.csv,
Employment statistics entity,
Contains information relating to student employment outcomes,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

ENTRY.csv
Entry qualifications entity,
Contains information relating to the entry qualifications of students,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

GOSALARY.csv,
Salary entity,
Contains salary information of graduates,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

GOSECSAL.csv,
Sector salary entity,
Contains sector salary data,
Linked to KISCOURSE and SBJ entities using GOSECSBJ, KISMODE and KISLEVEL

GOVOICEWORK.csv,
Graduate voice entity,
Contains information on graduate voice in relation to work,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

INSTITUTION.csv,
Institution table,
This entity describes the reporting institution
Linked to KISCOURSE entity using PUBUKPRN and UKPRN

JOBLIST.csv,
Job list entity,
Contains information about common job types obtained by students,
Linked to COMMON entity using PUBUKPRN, KISCOURSEID, KISMODE and COMSBJ,
(Note COMSBJ may contain nulls)

JOBTYPE.csv,
Job type entity,
Contains information relating to the types of profession entered by students,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

KISAIM.csv, 
KIS Aim lookup table,
Contains the code and label for each KISAIM,
Lookup table,
(This lookup table may be linked to the KISCOURSE entity using KISAIMCODE)

KISCOURSE.csv,
KIS course entity,
This entity records details of KIS courses,
Linked to INSTITUTION entity using PUBUKPRN and UKPRN, and
Linked to child entities using PUBUKPRN, KISCOURSEID and KISMODE

LEO3.csv,
LEO3 entity,
Contains Longitudinal Education Outcomes earnings data - 3 year timepoint,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

LEO3SEC.csv,
LEO3 sector entity,
Contains sector Longitudinal Education Outcomes earnings data - 3 year timepoint,
Linked to KISCOURSE and SBJ entities using LEO3SECSBJ, KISMODE and KISLEVEL

LEO5.csv,
LEO5 entity,
Contains Longitudinal Education Outcomes earnings data - 5 year timepoint,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

LEO5SEC.csv,
LEO5 sector entity,
Contains sector Longitudinal Education Outcomes earnings data - 5 year timepoint,
Linked to KISCOURSE and SBJ entities using LEO5SECSBJ, KISMODE and KISLEVEL

LOCATION.csv,
Location lookup table,
Contains details for each teaching location,
Linked to COURSELOCATION using UKPRN and LOCID (to get location information for each KISCOURSEID)

NSS.csv,
NSS entity,
Contains the National Student Survey (NSS) results,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

NSSCountry.csv,
NSSCountry entity,
Contains the country specific National Student Survey (NSS) results,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

SBJ.csv,
Subject entity,
Contains CAH level subject codes for each KISCourse,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

TARIFF.csv,
Tariff entity,
Contains information relating to the entry tariff points of students,
Linked to KISCOURSE entity using PUBUKPRN, KISCOURSEID and KISMODE

TEFOutcome.csv
TEFOutcome entity,
Contains information relating to the Teaching and Excellence Framework (TEF) ratings

UCASCOURSEID.csv,
UCASCOURSEID entity,
Contains UCAS course identifiers for each COURSELOCATION,
Linked to COURSELOCATION entity using PUBUKPRN, KISCOURSEID, KISMODE and LOCID
