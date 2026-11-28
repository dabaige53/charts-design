//! Native runtime regressions share one integration binary to avoid repeated release LTO.

#[path = "regression/cli.rs"]
mod cli;
#[path = "regression/data.rs"]
mod data;
#[path = "regression/lifecycle.rs"]
mod lifecycle;
#[path = "regression/model.rs"]
mod model;
