fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure().compile_protos(&["../../proto/indexer.proto"], &proto_includes())?;
    Ok(())
}

fn proto_includes() -> Vec<String> {
    let mut dirs = vec!["../../proto".to_owned()];
    for c in &[
        "/usr/include",
        "/usr/local/include",
        "/opt/homebrew/include",
    ] {
        if std::path::Path::new(c)
            .join("google/protobuf/timestamp.proto")
            .exists()
        {
            dirs.push(c.to_string());
            break;
        }
    }
    dirs
}
