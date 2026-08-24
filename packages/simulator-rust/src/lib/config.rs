use lazy_static::lazy_static;

pub struct Config {
    pub port: u64,
    pub market_data_bucket: String,
    pub fred_api_key: String,
    pub eod_api_key: String,
    pub sentry_dsn: String,
    pub gcp_key_path: String,
    pub server_to_server_token: String,
    pub cors_allow_origin_ending_list: Vec<String>,
}

fn env_or(name: &str, default: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| default.to_string())
}

// All values default so the server can run locally with no environment
// configured: an empty MARKET_DATA_BUCKET selects synthetic market data (see
// market_data::downloaded_market_data), an empty SENTRY_DSN disables Sentry,
// and an empty SERVER_TO_SERVER_TOKEN disables the
// /update_daily_market_data_series endpoint. The FRED/EOD keys and GCP key
// path are only used by the market-data update paths, which require the
// corresponding env vars to be set.
lazy_static! {
    pub static ref CONFIG: Config = Config {
        port: env_or("PORT", "8080").parse().unwrap(),
        market_data_bucket: env_or("MARKET_DATA_BUCKET", ""),
        fred_api_key: env_or("FRED_API_KEY", ""),
        eod_api_key: env_or("EOD_API_KEY", ""),
        sentry_dsn: env_or("SENTRY_DSN", ""),
        gcp_key_path: env_or("GCP_KEY_PATH", ""),
        server_to_server_token: env_or("SERVER_TO_SERVER_TOKEN", ""),
        cors_allow_origin_ending_list: std::env::var("CORS_ALLOW_ORIGIN_ENDING_LIST")
            .map(|value| value.split(',').map(|s| s.to_string()).collect())
            .unwrap_or_default(),
    };
}
