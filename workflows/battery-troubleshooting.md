---
workflow: battery-troubleshooting
skill: workflow-orchestrator
description: Battery drain and power management analysis for Android devices

output:
  dir: ./battery-analysis-output
  filename: "battery_{{timestamp}}.txt"

default_max_lines: 200

input:
  - path: "logcat*.txt"
    skill: android-log-analysis
    include:
      - ../templates/log/wakelock.yaml
      - ../templates/log/power.yaml
    templates:
      - id: high_drain
        pattern: "drain_rate.*[5-9][0-9]%|mDischargeCurrentLevel.*[5-9][0-9]"
        context_lines: 5
        description: >
          Abnormally high battery drain rate (>50%). Indicates aggressive
          background activity, a hardware issue, or a misbehaving app.
        post_process: decode_wakelock.py
        summary_prompt: >
          Identify the highest drain rate events. Note timestamps and any
          correlating wakelocks or services active at the time. Flag any
          drain rate above 5%/hr during screen-off periods as critical.

      - id: thermal_event
        pattern: "thermal|temperature.*(hot|critical|shutdown|throttl)"
        context_lines: 3
        description: >
          Thermal events and temperature warnings. High temperature accelerates
          battery drain and can cause throttling or emergency shutdown.

  - path: "bugreport*.txt"
    skill: android-log-analysis
    include:
      - ../templates/log/ril.yaml
    templates:
      - id: modem_wakeup
        pattern: "modem.*wakeup|wakeup.*modem|WAKEUP.*RIL"
        context_lines: 5
        description: >
          Modem wakeup events found in bugreport. Frequent modem wakeups
          prevent deep sleep and are a significant source of battery drain.
        summary_prompt: >
          Count modem wakeup events and estimate frequency. Determine if
          the modem is waking the device more than once per minute, which
          would indicate a network or configuration issue.

final_summary_prompt: >
  Based on all pattern findings above, provide a concise battery troubleshooting
  report including: (1) root cause hypothesis, (2) top 3 most suspicious events
  with timestamps, (3) which component is most likely responsible (app, modem,
  sensor, etc.), and (4) recommended next diagnostic steps.
---

# Battery Troubleshooting

Run using the `workflow-orchestrator` skill.
