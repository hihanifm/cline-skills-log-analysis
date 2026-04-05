---
workflow: battery-troubleshooting
skill: lens-workflow-orchestrator-agent
description: Battery drain and power management analysis for Android devices


default_max_lines: 200

input:
  - path: "logcat*.txt"
    include:
      - log/wakelock.yaml
      - log/power.yaml
      - log/battery-drain.yaml

  - path: "bugreport*.txt"
    include:
      - log/ril.yaml
      - log/modem-wakeup.yaml

final_summary_prompt: >
  Based on all pattern findings above, provide a concise battery troubleshooting
  report including: (1) root cause hypothesis, (2) top 3 most suspicious events
  with timestamps, (3) which component is most likely responsible (app, modem,
  sensor, etc.), and (4) recommended next diagnostic steps.
---

# Battery Troubleshooting

Run using the `lens-workflow-orchestrator-agent` skill.
