## AlgoBot-Footprint
...
``` 
      [Visualization Of The Project Structure]
  ┌────────────────┬────────────────────────────────────────────────────────────────────────────┐
            ┌── [MAIN] ──┐ 
   [START]- ↓ [L1-CHECK] ↑ -[START|CHECK|KILL-PROC'S]
            └ [WATCHDOG] ┘                  
               ↓ [IF] ↑       [G-SLEEP]            [SETSTATUS] <-[IF]-[L2-CHECK]
    ┌──────────┘      |         ↑                                        ↑
    |                 |       [IF] - ┌─── [MONITORING] -> [REALTIME STATUS & JITTER & LAG]
    |                 |              ↑
    |                 └───── [STATUS & TIME] <-[SET]-[MONITOR]-[GET]-> [STATUS]-> [RETURN BOOL]
    |                                                    ↑
    |                                         [SETSTATUS & GETSTATUS]
    |                              ┌─────────────────────┬────────────────────────────┐  
    |                     [SHM-S]  |-[RAW]         [RAW]-|-[GRID][SIGN]  [GRID][SIGN]-|
    |                              ↑                     ↑                            ↑
    |   [SLEEP-SEM'S] --wakeup--> [NETWORK] --wakeup--> [PARSING] --wakeup-->   [LOGIC]
    ↓         ↑                       ↓                     ↓                         ↓
    [GENERAL-SLEEP|TIMEOUT] <- [IF] ────────────────────── LOOP ──────────────────────┘
  └─────────────────────────────────────────────────────────────────────────────────────────────┘      
```
# FootprintEngine: Doc
...
ExampleValuesIDY: IDY=9_000, IDY_CENTER=10_000, TICKSIZE=0.01, BASEPRICE=100, PRICE=110
PRICE -> ID-Y: int(((base_price - price) / tick_size) + base_price).
Example: ID-Y = int(((100 - 110) / 0.01) + 10_000) -> 9000
ID-Y -> PRICE: ((idy_center - idy) * tick_size) + base_price.
Example: PRICE = ((10_000 - 9_000)) * 0.01) + 100 -> 110

Timestamp -> IDX: ((timestamp - base_timestamp)) // interval_in_milisecond * 2) + (0 if is_sell else 1)
IDX -> Timestamp: ...
```
         [2-D.Array "GRID" Visualization]
  ┌────────────────────────┬─────────────────────────────────────┐
                      [FOOTPRINT]
            [CLASTER-1][CLASTER-1]  [...]
            ╔═════════╦═════════╦══════════╗
            ║COL0║COL1║COL2║COL3║COL-X║COL-X 
            ╚═════════╩═════════╩══════════╝    
      ROW-0 ║ BID║ASK ║ BID║ASK ║ ...║ ... ║ 
      ROW-1 ║ 1.0║1.5 ║ 0.5║4.1 ║ ...║ ... ║ 
      ROW-Y ║ ...║... ║ ...║... ║ ...║ ... ║ 
    ROW'S-Y ║========== HEADERS ===========║  
    ROW-100 ║ ...║... ║ ...║... ║ ...║ ... ║ OPEN
    ROW-101 ║ ...║... ║ ...║... ║ ...║ ... ║ HIGH
    ROW-102 ║ ...║... ║ ...║... ║ ...║ ... ║ LOW
    ROW-103 ║ ...║... ║ ...║... ║ ...║ ... ║ CLOSE
    ROW'S-Y ║ ...║... ║ ...║... ║ ...║ ... ║ Exp. Delta, OI ...
            ╚═════════╩═════════╩══════════╝
  └──────────────────────────────────────────────────────────────┘
```
