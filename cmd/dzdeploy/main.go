package main

import (
	"github.com/jsirianni/dzdeploy/internal/deploycli"
	"os"
)

func main() { os.Exit(deploycli.Main(os.Args[1:])) }
