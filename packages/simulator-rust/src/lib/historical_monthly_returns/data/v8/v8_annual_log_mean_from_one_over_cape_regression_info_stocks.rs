use crate::{
    historical_monthly_returns::data::{
        AnnualLogMeanFromOneOverCAPERegressionInfo, FiveTenTwentyThirtyYearsSlopeAndIntercept,
    },
    shared_types::SlopeAndIntercept,
};

pub const V8_ANNUAL_LOG_MEAN_FROM_ONE_OVER_CAPE_REGRESSION_INFO_STOCKS:
    AnnualLogMeanFromOneOverCAPERegressionInfo = AnnualLogMeanFromOneOverCAPERegressionInfo {
    full: FiveTenTwentyThirtyYearsSlopeAndIntercept {
        five_year: SlopeAndIntercept {
            slope: 1.0083388192287381,
            intercept: -0.002119182397104735,
        },
        ten_year: SlopeAndIntercept {
            slope: 0.8778341120453834,
            intercept: 0.004572350814555447,
        },
        twenty_year: SlopeAndIntercept {
            slope: 0.5957717473741801,
            intercept: 0.02150207302372391,
        },
        thirty_year: SlopeAndIntercept {
            slope: 0.24985911409076594,
            intercept: 0.04523652254459053,
        },
    },
    restricted: FiveTenTwentyThirtyYearsSlopeAndIntercept {
        five_year: SlopeAndIntercept {
            slope: 0.94928521738416,
            intercept: 0.01585507211579091,
        },
        ten_year: SlopeAndIntercept {
            slope: 1.0713167988065262,
            intercept: 0.0022337507489408742,
        },
        twenty_year: SlopeAndIntercept {
            slope: 0.8338268834759505,
            intercept: 0.008024318290027574,
        },
        thirty_year: SlopeAndIntercept {
            slope: 0.2552376595376608,
            intercept: 0.046136419780549796,
        },
    },
};        
        