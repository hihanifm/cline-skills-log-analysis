---
workflow: emergency-call-troubleshooting
skill: lens-workflow-orchestrator-agent
description: Emergency call (E911/SOS) failure analysis for Android devices


default_max_lines: 200

input:
  - path: "logcat*.txt"
    include:
      - log/ims-sip.yaml
      - log/ril.yaml
      - log/emergency-call.yaml

  - path: "bugreport*.txt"
    include:
      - log/ril.yaml
      - log/network-coverage.yaml

final_summary_prompt: >
  Based on all pattern findings, provide an emergency call troubleshooting report:
  (1) Did the emergency call attempt succeed? If not, at which layer did it fail?
  (2) Was IMS/VoLTE available or did it fall back to CS?
  (3) Was there a coverage issue (no service / poor signal)?
  (4) Root cause hypothesis and recommended fix or escalation path.
---

# Emergency Call Troubleshooting

Run using the `lens-workflow-orchestrator-agent` skill.
