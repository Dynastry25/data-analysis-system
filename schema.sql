-- =========================================================
-- Data Analysis Platform - MVP Database Schema (PostgreSQL)
-- =========================================================

-- Users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Datasets (faili walizopakia)
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,          -- csv, xlsx
    row_count INTEGER,
    column_count INTEGER,
    status VARCHAR(20) DEFAULT 'uploaded',   -- uploaded, cleaned, analyzed
    uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Metadata ya kila column katika dataset
CREATE TABLE dataset_columns (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    column_name VARCHAR(150) NOT NULL,
    data_type VARCHAR(30),                   -- numeric, text, date, boolean
    missing_count INTEGER DEFAULT 0,
    unique_count INTEGER
);

-- Log ya vitendo vya cleaning
CREATE TABLE cleaning_actions (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,        -- drop_duplicates, fill_missing, drop_column
    parameters JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Matokeo ya uchambuzi (statistics)
CREATE TABLE analysis_results (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,      -- descriptive_stats, correlation, regression
    result_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Michoro (charts) iliyotengenezwa
CREATE TABLE charts (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    chart_type VARCHAR(30) NOT NULL,         -- bar, line, scatter, histogram
    config JSONB NOT NULL,                   -- columns, rangi, mipangilio
    created_at TIMESTAMP DEFAULT NOW()
);

-- Ripoti zilizopakuliwa (exported reports)
CREATE TABLE exported_reports (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_format VARCHAR(10) NOT NULL,        -- pdf, xlsx
    storage_path VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes muhimu kwa speed
CREATE INDEX idx_datasets_user ON datasets(user_id);
CREATE INDEX idx_dataset_columns_dataset ON dataset_columns(dataset_id);
CREATE INDEX idx_analysis_results_dataset ON analysis_results(dataset_id);
CREATE INDEX idx_charts_dataset ON charts(dataset_id);
