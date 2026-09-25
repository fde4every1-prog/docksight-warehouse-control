# Security, safety and autonomy constraints

The training repo never connects to physical control systems. Target designs should distinguish observe/recommend/reversible low-risk automation from material operational changes and safety-critical actions. Safety-system overrides, e-stop bypass, safety PLC changes and robot speed-limit changes require strong external authority and should not be autonomously delegated.
