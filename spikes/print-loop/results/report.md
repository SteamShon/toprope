# Pipeline report

Spec: `specs/airtag_holder.yaml`

| Item | Result | Print time | Filament | Unit cost |
|---|---|---|---|---|
| keyring-blank | PASS | 8m 39s | 3.31 g | $0.12 |
| keyring-name | PASS | 11m 33s | 5.1 g | $0.18 |
| collar-20mm | PASS | 14m 47s | 7.41 g | $0.24 |
| collar-25mm | PASS | 12m 20s | 6.03 g | $0.2 |
| bike-cage-mount | PASS | 24m 26s | 10.26 g | $0.36 |
| tolerance-coupon | PASS | 22m 56s | 13.82 g | $0.43 |

Cost assumptions: filament_usd_per_kg=20.0, machine_usd_per_hour=0.3, failure_rate=0.1

## keyring-blank

- ✅ solid: valid=True, solids=1
- ✅ fits Bambu Lab A1 (256 mm): size (36.3, 38.2, 11.6) mm
- ✅ fits Bambu Lab A1 mini (180 mm): size (36.3, 38.2, 11.6) mm
- ✅ min wall: wall 2.0 mm, roof 1.2 mm >= 1.2 mm
- ✅ R2 tag sits free in pocket: overlap with tag 0.000 mm3
- ✅ R2 lip stops tag falling out the front: overlap after +0.5 mm z: 22.1 mm3
- ✅ R2 detents stop tag sliding out: overlap after +7 mm y: 4.3 mm3
- ✅ R2 detent clicks (not too tight): interference 0.60 mm (0-1.0)
- ✅ R3 speaker window: front window 29.3 mm
- ✅ R1 keyring hole: 5.5 mm hole
- ✅ slices: 8m 39s

## keyring-name

- ✅ solid: valid=True, solids=1
- ✅ fits Bambu Lab A1 (256 mm): size (36.3, 49.2, 11.6) mm
- ✅ fits Bambu Lab A1 mini (180 mm): size (36.3, 49.2, 11.6) mm
- ✅ min wall: wall 2.0 mm, roof 1.2 mm >= 1.2 mm
- ✅ R2 tag sits free in pocket: overlap with tag 0.000 mm3
- ✅ R2 lip stops tag falling out the front: overlap after +0.5 mm z: 22.1 mm3
- ✅ R2 detents stop tag sliding out: overlap after +7 mm y: 4.3 mm3
- ✅ R2 detent clicks (not too tight): interference 0.60 mm (0-1.0)
- ✅ R3 speaker window: front window 29.3 mm
- ✅ R1 keyring hole: 5.5 mm hole
- ✅ slices: 11m 33s

## collar-20mm

- ✅ solid: valid=True, solids=1
- ✅ fits Bambu Lab A1 (256 mm): size (36.3, 47.3, 14.7) mm
- ✅ fits Bambu Lab A1 mini (180 mm): size (36.3, 47.3, 14.7) mm
- ✅ min wall: wall 2.0 mm, roof 1.2 mm >= 1.2 mm
- ✅ R2 tag sits free in pocket: overlap with tag 0.000 mm3
- ✅ R2 lip stops tag falling out the front: overlap after +0.5 mm z: 22.1 mm3
- ✅ R2 detents stop tag sliding out: overlap after +7 mm y: 4.3 mm3
- ✅ R2 detent clicks (not too tight): interference 0.60 mm (0-1.0)
- ✅ R3 speaker window: front window 29.3 mm
- ✅ R1 strap fits: tunnel 21.0 x 3.3 mm for 20 x 2.5 mm strap
- ✅ slices: 14m 47s

## collar-25mm

- ✅ solid: valid=True, solids=1
- ✅ fits Bambu Lab A1 (256 mm): size (36.3, 36.3, 15.2) mm
- ✅ fits Bambu Lab A1 mini (180 mm): size (36.3, 36.3, 15.2) mm
- ✅ min wall: wall 2.0 mm, roof 1.2 mm >= 1.2 mm
- ✅ R2 tag sits free in pocket: overlap with tag 0.000 mm3
- ✅ R2 lip stops tag falling out the front: overlap after +0.5 mm z: 22.1 mm3
- ✅ R2 detents stop tag sliding out: overlap after +7 mm y: 4.3 mm3
- ✅ R2 detent clicks (not too tight): interference 0.60 mm (0-1.0)
- ✅ R3 speaker window: front window 29.3 mm
- ✅ R1 strap fits: tunnel 26.0 x 3.8 mm for 25 x 3.0 mm strap
- ✅ slices: 12m 20s

## bike-cage-mount

- ✅ solid: valid=True, solids=1
- ✅ fits Bambu Lab A1 (256 mm): size (36.3, 78.0, 14.1) mm
- ✅ fits Bambu Lab A1 mini (180 mm): size (36.3, 78.0, 14.1) mm
- ✅ min wall: wall 2.0 mm, roof 1.2 mm >= 1.2 mm
- ✅ R2 tag sits free in pocket: overlap with tag 0.000 mm3
- ✅ R2 lip stops tag falling out the front: overlap after +0.5 mm z: 22.1 mm3
- ✅ R2 detents stop tag sliding out: overlap after +7 mm y: 4.3 mm3
- ✅ R2 detent clicks (not too tight): interference 0.60 mm (0-1.0)
- ✅ R3 speaker window: front window 29.3 mm
- ✅ R1 bolt pattern: 64 mm spacing clears the pocket
- ✅ slices: 24m 26s

## tolerance-coupon

- ✅ solid: solids=1
- ✅ slices: 22m 56s
