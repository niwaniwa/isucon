package main

import (
	"html/template"
	"sync"
)

var (
	templateCache = make(map[string]*template.Template)
	templateMutex sync.RWMutex
)

// getTemplate returns a cached template or creates a new one
func getTemplate(name string, funcMap template.FuncMap, files ...string) (*template.Template, error) {
	// Create cache key from template files
	cacheKey := name
	for _, f := range files {
		cacheKey += ":" + f
	}
	
	// Check cache first
	templateMutex.RLock()
	if tmpl, ok := templateCache[cacheKey]; ok {
		templateMutex.RUnlock()
		return tmpl, nil
	}
	templateMutex.RUnlock()
	
	// Create new template
	var tmpl *template.Template
	var err error
	
	if funcMap != nil {
		tmpl, err = template.New(name).Funcs(funcMap).ParseFiles(files...)
	} else {
		tmpl, err = template.ParseFiles(files...)
	}
	
	if err != nil {
		return nil, err
	}
	
	// Cache the template
	templateMutex.Lock()
	templateCache[cacheKey] = tmpl
	templateMutex.Unlock()
	
	return tmpl, nil
}