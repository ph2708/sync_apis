-- Schema para armazenar dados da API eTrac
-- Cria um schema dedicado `e_track` e define o search_path para evitar poluição do schema `public`.
CREATE SCHEMA IF NOT EXISTS e_track;
SET search_path = e_track, public;
CREATE TABLE IF NOT EXISTS terminals (
    placa TEXT PRIMARY KEY,
    descricao TEXT,
    frota TEXT,
    equipamento_serial TEXT,
    data_gravacao TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT now(),
    data JSONB
);

CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    placa TEXT REFERENCES terminals(placa) ON DELETE CASCADE,
    data_transmissao TIMESTAMP,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    logradouro TEXT,
    velocidade INTEGER,
    ignicao BOOLEAN,
    odometro DOUBLE PRECISION,
    odometro_can DOUBLE PRECISION,
    horimetro DOUBLE PRECISION,
    bateria DOUBLE PRECISION,
    equipamento_serial TEXT,
    data_gravacao TIMESTAMP,
    raw JSONB,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS positions_placa_idx ON positions(placa);
CREATE INDEX IF NOT EXISTS positions_data_transmissao_idx ON positions(data_transmissao);

CREATE TABLE IF NOT EXISTS trips (
    id BIGSERIAL PRIMARY KEY,
    placa TEXT,
    cliente TEXT,
    cliente_fantasia TEXT,
    data_inicio_conducao TIMESTAMP,
    data_fim_conducao TIMESTAMP,
    latitude_inicio_conducao DOUBLE PRECISION,
    longitude_inicio_conducao DOUBLE PRECISION,
    latitude_fim_conducao DOUBLE PRECISION,
    longitude_fim_conducao DOUBLE PRECISION,
    localizacao_inicio_conducao TEXT,
    localizacao_fim_conducao TEXT,
    odometro_inicio_conducao DOUBLE PRECISION,
    odometro_fim_conducao DOUBLE PRECISION,
    duracao_conducao INTERVAL,
    distancia_conducao DOUBLE PRECISION,
    condutor_nome TEXT,
    condutor_identificacao TEXT,
    raw JSONB,
    created_at TIMESTAMP DEFAULT now()
);

-- Routes table: stores per-vehicle per-day aggregated route as JSONB
CREATE TABLE IF NOT EXISTS routes (
    id BIGSERIAL PRIMARY KEY,
    placa TEXT NOT NULL,
    rota_date DATE NOT NULL,
    points JSONB NOT NULL,
    start_ts TIMESTAMP,
    end_ts TIMESTAMP,
    point_count INTEGER,
    created_at TIMESTAMP DEFAULT now(),
    raw JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS routes_placa_date_idx ON routes(placa, rota_date);
