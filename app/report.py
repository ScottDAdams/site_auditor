def generate_report(findings):
    report = "SITE AUDIT REPORT\n\n"

    for f in findings:
        report += f"- {f['type']} [{f['priority']}]\n"
        for p in f["pages"]:
            report += f"  - {p}\n"
        report += "\n"

    return report
