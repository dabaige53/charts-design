use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
};

fn files(root: &Path, directory: &Path, rust_only: bool, output: &mut Vec<PathBuf>) {
    println!("cargo:rerun-if-changed={}", directory.display());
    for entry in fs::read_dir(directory).expect("read build inputs") {
        let entry = entry.expect("build input entry");
        let kind = entry.file_type().expect("build input type");
        let path = entry.path();
        if kind.is_dir() {
            files(root, &path, rust_only, output);
        } else if kind.is_file()
            && (!rust_only || path.extension().is_some_and(|value| value == "rs"))
        {
            output.push(path.strip_prefix(root).expect("package input").to_owned());
        }
    }
}

fn main() {
    let root = PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").expect("Cargo package root"));
    let mut inputs = vec![
        PathBuf::from("Cargo.toml"),
        PathBuf::from("Cargo.lock"),
        PathBuf::from("build.rs"),
    ];
    files(&root, &root.join("src"), true, &mut inputs);
    files(&root, &root.join("resources"), false, &mut inputs);
    inputs.sort();
    let mut hash = Sha256::new();
    for relative in inputs {
        println!("cargo:rerun-if-changed={}", relative.display());
        let name = relative.to_string_lossy().replace('\\', "/");
        let bytes = fs::read(root.join(&relative)).expect("read backend fingerprint input");
        hash.update((name.len() as u64).to_le_bytes());
        hash.update(name.as_bytes());
        hash.update((bytes.len() as u64).to_le_bytes());
        hash.update(bytes);
    }
    let fingerprint = format!("{:x}", hash.finalize());
    println!(
        "cargo:rustc-env=CHARTS_BACKEND_BUILD_ID={}",
        &fingerprint[..16]
    );
}
