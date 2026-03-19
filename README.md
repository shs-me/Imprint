# GridCore
...
``` 
                           [Visualization Of The GridCore Structure]
    ┌───────────────┬─────────────────────────────────────────────────────────────────────────────────────┐
              ┌── [MAIN] ──┐ 
      [INIT]- ↓ [L1-CHECK] ↑ -[START | KILL PROC'S | CLOSE CORE]
              └ [WATCHDOG] ┘                  
                   |  ↑      [G-SLEEP]       SETSTATUS]-[MODULE]<-[IF]-[L2-CHECK]
                   ↓  |        ↑                                          ↑
               [TASK] |      [IF] - ┌─── [MONITORING] -> [REALTIME STATUS & JITTER] -> [UDP] -> [BOARD]
                ↓     |             ↑
            [ACTION]  └── ─ [STATUS & TIME] <-[SET]-[MONITOR]-[GET]-> [STATUS]-> [RETURN BOOL]
   [ACTION] -[IF] ────┘                                 ↑
       ┌──────┘                                [SETSTATUS & GETSTATUS]
       |                            ┌─────────────────────┬──────────────────────────────────┐  
       |                   [SHM-S]  |-[RAW]         [RAW]-|-[GRID][METRICS]  [GRID][METRICS]-|-[METRICS]
       |                            ↑                     ↑                                  ↑
       |      ┌───┌─ --wakeup--> [NETWORK]  --wakeup--> [PARSING] --wakeup-->          [LOGIC]
       |      ↑   └─── [recv] ─── [IF] ──┘       ↑          ↓                                ↓
       ↓  ┌─ [--wakeup-->] ────────|─────> [SLEEP-SEM] <─ [IF] ──────────────────────────────┘
      [GENERAL-SLEEP|TIMEOUT] <────┘──────────────────────┘
    └─────────────────────────────────────────────────────────────────────────────────────────────────────┘         
```
# GridEngine
---
```
            [2-D.Array "GRID" Visualization]
  ┌────────────────────────┬─────────────────────────────────────┐
                      [FOOTPRINT]
            [CLASTER-1][CLASTER-1]  [...]
            ╔═════════╦═════════╦══════════╗
            ║IDX0║IDX1║IDX2║IDX3║ IDX'S-...║
            ╚═════════╩═════════╩══════════╝    
      IDY-0 ║ BID║ASK ║ BID║ASK ║ ...║ ... ║ 
      IDY-1 ║ 1.0║1.5 ║ 0.5║4.1 ║ ...║ ... ║ 
    IDY-... ║ ...║... ║ ...║... ║ ...║ ... ║ 
  IDY'S-... ║══════════ HEADERS ═══════════║  
    IDY-Y1  ║ ...║... ║ ...║... ║ ...║ ... ║ OPEN
    IDY-Y2  ║ ...║... ║ ...║... ║ ...║ ... ║ HIGH
    IDY-Y3  ║ ...║... ║ ...║... ║ ...║ ... ║ LOW
    IDY-Y4  ║ ...║... ║ ...║... ║ ...║ ... ║ CLOSE
  IDY'S-... ║ ...║... ║ ...║... ║ ...║ ... ║ Exp. Delta, OI ...
            ╚═════════╩═════════╩══════════╝
  └──────────────────────────────────────────────────────────────┘
```
>**Price -> ID-Y:**  $$idy =  IDYcenter + \frac{basePrice - price}{tickSize}$$
 >>**Example:** $$9'000 = 10'000 + \frac{100 - 110}{0.01}$$

>**ID-Y -> Price:** $$price = basePrice + (idyCenter - idy)\cdot tickSize$$
>>**Example:** $$110 = 100 + (10000 - 9000) \cdot 0.01$$

---
>**Timestamp -> ID-X:**  $$idx = \frac{timestamp - baseTimestamp}{range}\cdot 2 + side$$
>>**Example:** $$1 = \frac{1'773'906'698 - 1'773'906'534}{60000}\cdot 2 + 1$$
>>>**range**: interval **chart** in milisecond, exp $1min \cdot 60s \cdot 1000ms$ **, side:** 0 if **is_sell** else 1

>**ID-X -> Timestamp:**  $$timestamp = \frac{idx - side}{2}\cdot range + baseTimestamp $$
>>**Example:** $$1'773'906'698 = \frac{1 - 1}{2}\cdot60000 + 1'773'906'534$$
