package deploy

import (
	"path"
	"strings"
	"testing"
)

func FuzzSafeRelative(f *testing.F) {
	for _, seed := range []string{"serverDZ.cfg", "mpmissions/example/types.xml", "../secret", "/etc/passwd", `C:\secret`, "NUL.txt", "", "\x00"} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, name string) {
		if SafeRelative(name) != nil {
			return
		}
		// Accepted paths must remain relative and canonical across both client
		// platforms, with no Windows drive or separator reinterpretation.
		if name == "" || path.IsAbs(name) || path.Clean(name) != name ||
			strings.ContainsAny(name, "\\:\x00\r\n") {
			t.Fatalf("accepted unsafe portable relative path %q", name)
		}
		if err := SafeRelative(name + "/../escape"); err == nil {
			t.Fatal("accepted a traversal appended to a valid path")
		}
	})
}
