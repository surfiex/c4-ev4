import cereal.messaging as messaging


def debug_engagement():
  sm = messaging.SubMaster(['carState', 'carParams', 'controlsState'])
  print("Starting Engagement Debugger for Kia EV4 (v2.5)...")
  print("Press Ctrl+C to stop.\n")

  last_state = None
  while True:
    sm.update(100)
    if sm.updated['carState']:
      cs = sm['carState']

      # Status logic
      status = "UNKNOWN"
      state = "UNKNOWN"
      ctrls = None
      if sm.updated['controlsState'] or sm.alive['controlsState']:
        ctrls = sm['controlsState']

      # Blockers logic (D: Door, S: Seatbelt, G: Gas, B: Brake, C: Cruise)
      raw = f"D:{int(cs.doorOpen)} S:{int(cs.seatbeltUnlatched)} G:{int(cs.gasPressed)} B:{int(cs.brakePressed)} C:{int(cs.cruiseState.available)}"

      blockers = []
      if cs.gasPressed:
        blockers.append("Gas")
      if cs.brakePressed:
        blockers.append("Brake")
      if cs.doorOpen:
        blockers.append("Door")
      if cs.seatbeltUnlatched:
        blockers.append("Seatbelt")
      if not cs.cruiseState.available:
        blockers.append("CruiseOff")

      # Explicit Gear Check
      gear_str = str(cs.gearShifter)
      if "drive" not in gear_str.lower():
        blockers.append(f"Gear:{gear_str}")

      if ctrls:
        try:
          d = ctrls.to_dict()
          active = d.get('active', d.get('enabled', False))
          # Some versions use different field names
          curr_state = d.get('state', d.get('activeState', 'N/A'))
          state = str(curr_state)

          if active:
            status = "ENGAGED"
          elif not blockers:
            status = "READY"
          else:
            status = "BLOCKED"
        except Exception as e:
          state = f"ERR:{type(e).__name__}"

      # Print line
      print(f"\r{status:<10} | {state:<15} | {raw} | Blockers: {', '.join(blockers) if blockers else 'None':<25} | {cs.vEgo * 3.6:5.1f}km/h", end="")

      if last_state != state:
        if last_state is not None:
          print(f"\n[EVENT] State: {last_state} -> {state}")
          if "N/A" in state or "UNKNOWN" in state:
            if ctrls:
              print(f"[DIAG] controlsState available. Keys: {list(ctrls.to_dict().keys())}")
            else:
              print(f"[DIAG] controlsState NOT available (timeout/not alive)")
        last_state = state

      # Button detection - show ALL buttons
      for b in cs.buttonEvents:
        if b.pressed:
          print(f"\n[BUTTON] {b.type} (val: {int(b.pressed)}) | PCM: {cs.cruiseState.enabled}")


if __name__ == "__main__":
  debug_engagement()
