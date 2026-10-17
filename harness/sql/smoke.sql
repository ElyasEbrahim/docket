-- pg-jev README queries against the upstream mock API (keyless under /local/).
-- Mock rules: noul → 0.9 if the condition's LAST word appears in the row JSON, else 0.1;
-- choice/score → index = length(row JSON) mod n.
CREATE EXTENSION IF NOT EXISTS jev CASCADE;
SET jev.api_url = 'http://mock:8765/local/v1/systemone';
SET jev.notices = off;

DROP TABLE IF EXISTS smoke_tickets;
CREATE TEMP TABLE smoke_tickets (id int, subject text, body text);
INSERT INTO smoke_tickets VALUES
  (1, 'Refund please', 'I was double charged and I am angry'),
  (2, 'Login issue', 'Cannot sign in since the update'),
  (3, 'Cancel', 'I will cancel my plan, this is fraud'),
  (4, 'Question', 'How do I export invoices?');

SELECT jev_version();
SELECT id, subject FROM smoke_tickets WHERE jev(smoke_tickets, 'the customer is angry') ORDER BY id;
SELECT id, round(jev_prob(smoke_tickets, 'mentions fraud')::numeric, 2) AS p FROM smoke_tickets ORDER BY p DESC, id;
SELECT jev_choice(smoke_tickets, 'which team should handle this?',
                  ARRAY['billing', 'technical', 'security', 'sales']) AS team, count(*)
FROM smoke_tickets GROUP BY 1 ORDER BY 1;
SELECT id, jev_score(smoke_tickets, 'how urgent is this?', ARRAY['low', 'medium', 'high']) AS urgency
FROM smoke_tickets ORDER BY id;
SELECT jsonb_build_object('requests', s->'requests', 'rows_evaluated', s->'rows_evaluated',
                          'cache_hits', s->'cache_hits', 'errors', s->'errors') AS stats
FROM jev_stats() s;
