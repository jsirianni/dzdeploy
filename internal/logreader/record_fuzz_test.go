package logreader

import (
	"encoding/json"
	"testing"
)

func FuzzDecodeRecord(f *testing.F) {
	for _, seed := range []string{
		`{"level":"info","message":"ready","timestamp":"2026-01-01T00:00:00Z"}`,
		`{"level":"error","message":"\u0000\n","timestamp":"2026-01-01T00:00:00Z"}`,
		`{"level":"info","message":null,"timestamp":null}`,
		"", "{", "\xff",
	} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, line string) {
		record, ok := DecodeRecord(line)
		if !ok {
			return
		}
		if !json.Valid([]byte(line)) || record.Timestamp.IsZero() {
			t.Fatal("accepted invalid JSON record")
		}
		roundTrip, accepted := DecodeRecord(encodeRecord(record))
		if !accepted || roundTrip.Level != record.Level || roundTrip.Message != record.Message ||
			!roundTrip.Timestamp.Equal(record.Timestamp) {
			t.Fatalf("accepted record did not round trip: %#v", record)
		}
	})
}
