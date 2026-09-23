fn main() -> Result<(), Box<dyn std::error::Error>> {
    let includes = proto_includes();
    tonic_build::configure().compile_protos(&["../../proto/memory.proto"], &includes)?;
    Ok(())
}

/// Returns the list of proto include directories:
/// - The project's own proto/ dir
/// - The system well-known types dir (installed by libprotobuf-dev or protobuf on macOS)
fn proto_includes() -> Vec<String> {
    let mut dirs = vec!["../../proto".to_owned()];

    // Linux (libprotobuf-dev): /usr/include
    // macOS (brew install protobuf): $(brew --prefix)/include
    for candidate in &[
        "/usr/include",
        "/usr/local/include",
        "/opt/homebrew/include",
    ] {
        if std::path::Path::new(candidate)
            .join("google/protobuf/timestamp.proto")
            .exists()
        {
            dirs.push(candidate.to_string());
            break;
        }
    }
    dirs
}
