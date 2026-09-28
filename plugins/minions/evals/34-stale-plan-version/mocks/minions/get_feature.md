---
expect:
  key: string
---
{"key":"{{input.key}}","title":"Checkout modernization","status":"In Progress","phase":{"key":"building","label":"Building","detail":null,"blocker":null},"paused":false,"plan":{"document":"Wave 1","planVersion":"plan-version-42"},"children":[{"key":"PLAN-43","title":"First wave","wave":1,"status":"Done","dependsOn":null,"prUrl":null}],"progress":{"total":1,"done":1,"inFlight":0,"blocked":0,"byWave":[{"wave":1,"total":1,"done":1}]},"actions":{"merge":{"allowed":false,"reason":"Feature is not ready to merge."},"retryReview":{"allowed":false,"reason":"Feature review is not escalated."},"pause":{"allowed":true,"reason":null},"resume":{"allowed":false,"reason":"Feature is not paused."},"addWave":{"allowed":true,"reason":null}}}
