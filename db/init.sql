CREATE TABLE IF NOT EXISTS emails (
    id    SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
CREATE TABLE IF NOT EXISTS phones (
    id           SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL
);
INSERT INTO emails (email) VALUES ('ivanov@mail.ru'), ('test.user@example.com');
INSERT INTO phones (phone_number) VALUES ('+79991234567'), ('88005553535');
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'repl_user') THEN
        CREATE ROLE repl_user WITH REPLICATION LOGIN PASSWORD 'repl_password';
    END IF;
END $$;
