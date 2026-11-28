use super::*;
// @wu-test type=unit | scope=model | protects=chart references cannot hide in malformed or nested report fences
#[test]
fn report_fences_preserve_markdown_contract() {
    assert_eq!(
        report_chart_references("```chart\n{\"componentId\":\"sales\"}\n```", None).unwrap(),
        vec!["sales"]
    );
    assert!(report_chart_references(
        "```chart\n{\"componentId\":\"sales\",\"componentId\":\"other\"}\n```",
        None
    )
    .is_err());
    assert!(report_chart_references("> ```chart\n> {}\n> ```", None).is_err());
    assert!(
        report_chart_references("````text\n```chart\n{}\n```\n````", None)
            .unwrap()
            .is_empty()
    );
}
