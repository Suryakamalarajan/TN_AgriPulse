CREATE DATABASE IF NOT EXISTS tn_agripulse;
USE tn_agripulse;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(191) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'USER',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_auth_users_role (role)
);

CREATE TABLE IF NOT EXISTS market_prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    market VARCHAR(150) NOT NULL,
    commodity VARCHAR(120) NOT NULL,
    variety VARCHAR(150) DEFAULT NULL,
    arrival_date DATE NOT NULL,
    min_price DECIMAL(12,2) DEFAULT NULL,
    max_price DECIMAL(12,2) DEFAULT NULL,
    modal_price DECIMAL(12,2) DEFAULT NULL,
    price_unit VARCHAR(50) DEFAULT 'INR/Qtl',
    source VARCHAR(120) NOT NULL,
    source_record_id VARCHAR(200) DEFAULT NULL,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_market_prices_filters (state, district, commodity, arrival_date),
    KEY idx_market_prices_market (market, commodity)
);

CREATE TABLE IF NOT EXISTS data_sync_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(80) NOT NULL,
    source VARCHAR(120) DEFAULT 'data.gov.in',
    records_imported INT DEFAULT 0,
    total_pages INT DEFAULT 0,
    error_summary TEXT DEFAULT NULL,
    api_status VARCHAR(80) DEFAULT NULL
);
