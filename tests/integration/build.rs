fn main() -> Result<(), Box<dyn std::error::Error>> {
    let includes = proto_includes();
    tonic_build::configure().compile_protos(
        &[
            "../../proto/memory.proto",
            "../../proto/indexer.proto",
            "../../proto/policy.proto",
            "../../proto/context.proto",
            "../../proto/bus.proto",
            "../../proto/optimizer.proto",
        ],
        &includes,
    )?;
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
