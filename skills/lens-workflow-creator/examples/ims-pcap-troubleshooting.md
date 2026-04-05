---
workflow: ims-pcap-troubleshooting
skill: lens-workflow-orchestrator-agent
description: IMS/VoLTE network capture analysis — SIP signaling and DNS for call and registration issues


default_max_lines: 200

input:
  - path: "*.pcap*"
    include:
      - pcap/sip.yaml
      - pcap/dns.yaml
      - pcap/volte.yaml

final_summary_prompt: >
  Based on all SIP and DNS findings, provide an IMS/VoLTE troubleshooting report:
  (1) Did IMS registration succeed? If not, why?
  (2) Did any VoLTE call attempt succeed? Trace the complete call flow.
  (3) Were there any DNS failures affecting IMS connectivity?
  (4) Root cause hypothesis and recommended next steps.
---

# IMS PCAP Troubleshooting

Run using the `lens-workflow-orchestrator-agent` skill.
