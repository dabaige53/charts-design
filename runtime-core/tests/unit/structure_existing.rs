use super::*;
// @wu-test type=unit | scope=structure | protects=executable SVG and external paints never enter saved diagrams
#[test]
fn sanitizes_active_svg() {
    let output=sanitize_svg(r#"<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script><rect width="20" fill="url(https://bad)"/><text>A &amp; B</text></svg>"#,&json!([0,0,100,100])).unwrap();
    assert!(!output.contains("script"));
    assert!(!output.contains("onload"));
    assert!(!output.contains("https"));
    assert!(output.contains("A &amp; B"));
    assert!(sanitize_svg("<!DOCTYPE svg><svg/>", &json!([0, 0, 1, 1])).is_err());
}
