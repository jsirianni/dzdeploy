package main

import (
	"os"

	"github.com/jsirianni/dzdeploy/internal/deploycli"
)

func main() { os.Exit(deploycli.Main(os.Args[1:])) }
