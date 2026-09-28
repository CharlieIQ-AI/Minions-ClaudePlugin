---
expect:
  key: string
---
{"key":"{{input.key}}","title":"Checkout modernization","status":"Ready for Merge","phase":{"key":"ready_to_merge","label":"Ready to merge","detail":null,"blocker":null},"paused":false,"plan":{"document":"Wave 1","planVersion":"plan-version-42"},"children":[{"key":"PLAN-43","title":"First wave","wave":1,"status":"Done","dependsOn":null,"prUrl":"https://github.com/example/repo/pull/43"}],"progress":{"total":1,"done":1,"inFlight":0,"blocked":0,"byWave":[{"wave":1,"total":1,"done":1}]},"actions":{"merge":{"allowed":true,"reason":null},"retryReview":{"allowed":false,"reason":"Feature review is not escalated."},"pause":{"allowed":true,"reason":null},"resume":{"allowed":false,"reason":"Feature is not paused."},"addWave":{"allowed":true,"reason":null}}}
