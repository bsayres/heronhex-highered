# Brief data schema for `assets/dashboard.html`

Replace only the JSON inside `<script id="brief-data" type="application/json">`. Every value comes from a tool result, copied as returned. Use `null` for anything a tool returned as null or did not return. Never compute, round, estimate or fill. Escape `</` as `<\/` inside the JSON.

```json
{
  "institution": {"name": "", "city": "", "state": "", "control": "", "unitid": ""},
  "generated": "YYYY-MM-DD",
  "enrollment": {
    "series": [{"year": 2015, "value": 2257}],
    "peers": [{"unitid": "", "name": "", "series": [{"year": 2015, "value": 0}]}]
  },
  "finance": [{"year": 2023, "revenue": 0, "expenses": 0, "state_appropriations": 0, "net_tuition": 0}],
  "risk": {
    "hcm": {"listed": false, "as_of": "YYYY-MM-DD"},
    "composite": [{"year": "2020-21", "score": 0.0}],
    "cdr": [{"year": "FY2021", "rate": 0.0}],
    "audits": [{
      "fy_end": "YYYY-MM-DD", "finding_count": 0, "months_to_submission": 0.0,
      "findings": [{"ref": "", "requirement": "", "program": "", "material_weakness": false, "questioned_costs": false}]
    }]
  },
  "accreditation": [{"agency": "", "scope": "institutional|programmatic", "program": "", "current": true,
                     "end_date": null, "last_action": null, "last_action_date": null}],
  "programs": [{"program": "", "cip4": "", "credential": "", "awards": 0,
                "earnings_institution": null, "earnings_national": null}],
  "gaps": [{"field": "risk.composite", "reason": "reason string from the tool's null"}],
  "sources": [{"name": "", "as_of": "", "retrieved_at": ""}]
}
```

## Where each key comes from

| Key | Tool and field |
|---|---|
| `institution.*` | `get_institution_profile`: `name`, `city`, `state`, `control`, `identifiers.unitid` |
| `enrollment.series` | `get_enrollment_trend`: `rows` of `[year, enrollment_fall]` |
| `enrollment.peers[*].series` | `compare_peers`: `rows` of `[unitid, name, year, enrollment_fall, is_target]`; group the rows where `is_target` is false by `unitid` |
| `finance` | `get_financial_snapshot(years>=2)`: `history.rows` with columns `year`, `total_revenues`→`revenue`, `total_expenses`→`expenses`, `state_appropriations`, `net_tuition_and_fees`→`net_tuition` |
| `risk.hcm` | `get_title_iv_status`: `heightened_cash_monitoring.listed`, `.as_of` |
| `risk.composite`, `risk.cdr` | `get_title_iv_status`: `financial_responsibility`, `cohort_default_rates`; if null, leave the arrays empty and add a `gaps` entry with the tool's reason |
| `risk.audits` | `get_audit_findings`: per audit `fy_end`, `finding_count`, `filing_timeline.months_from_fy_end_to_submission`; per finding `reference_number`→`ref`, `compliance_requirement_labels` joined→`requirement`, `program.name`→`program`, `material_weakness`, `questioned_costs` |
| `accreditation` | `get_accreditation_status`: `accreditors[*]` with `agency_name`→`agency`, `scope`, `program`, `current`, `end_date`, `last_action.action`/`.date` |
| `programs` | `get_program_outcomes`: `rows` with `program`, `cip4`, `credential`, the latest awards column→`awards`, `earnings_1yr_median_institution`→`earnings_institution`, `earnings_1yr_median_national`→`earnings_national` |
| `gaps` | every `nulls[]` entry the tools returned: `field`, `reason`. Prefix `field` with the section key (`enrollment`, `finance`, `risk`, `accreditation`, `programs`) so the page shows it under that section |
| `sources` | every response's `sources[]`: `source`→`name`, `as_of`, `retrieved_at` |

## What the page computes (and nothing else)

Latest-year tiles, the change in enrollment between the first and last years in the data, counts of current and ended accreditation records, filter counts. It does not forecast, smooth, rank or score.

## After filling it in

Give the user a short reconciliation: for each tile, the tool and field it came from. Then state the year or date range of every chart.
