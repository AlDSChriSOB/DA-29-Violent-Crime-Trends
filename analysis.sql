SELECT "year" AS segment, COUNT(*) AS rows_used, AVG("violent") AS metric, MIN("violent") AS minimum, MAX("violent") AS maximum FROM observations GROUP BY "year" ORDER BY "year";
