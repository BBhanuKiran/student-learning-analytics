SEED ?= 20261022
install:        ; pip install -r requirements.txt
test:           ; python -m pytest -q tests
tiny:           ; python -m edu_synth.generate --scale tiny --seed $(SEED) --out output/tiny --sql-seed
starter:        ; python -m edu_synth.generate --scale starter --seed $(SEED) --out output/starter --sql-seed
full:           ; python -m edu_synth.generate --scale full --seed $(SEED) --out output/full
repro-tiny:     ; python scripts/check_reproducibility.py --scale tiny --out reports/reproducibility_tiny.json
repro-full:     ; python scripts/check_reproducibility.py --scale full --skip-other-seed --out reports/reproducibility_full.json
