package restapi

import (
	"log/slog"

	"github.com/danielmiessler/fabric/core"
	"github.com/gin-gonic/gin"
)

func Serve(registry *core.PluginRegistry, address string, apiKey string) (err error) {
	r := gin.New()

	// Add CORS middleware before any routes
	r.Use(CORSMiddleware())

	// Middleware
	r.Use(gin.Logger())
	r.Use(gin.Recovery())

	if apiKey != "" {
		r.Use(APIKeyMiddleware(apiKey))
	} else {
		slog.Warn("Starting REST API server without API key authentication. This may pose security risks.")
	}

	// Register routes
	fabricDb := registry.Db
	NewPatternsHandler(r, fabricDb.Patterns)
	NewContextsHandler(r, fabricDb.Contexts)
	NewSessionsHandler(r, fabricDb.Sessions)
	NewChatHandler(r, registry, fabricDb)
	NewConfigHandler(r, fabricDb)
	NewModelsHandler(r, registry.VendorManager)
	NewStrategiesHandler(r)

	// Agents routes for Agno service
	r.POST("/agents/orchestrate", OrchestrateHandler())
	r.GET("/agents/files/output.pptx", FileProxyHandler())
	// Streaming orchestration and logs
	r.POST("/agents/generate-stream", OrchestrateStreamHandler())
	r.GET("/agents/runs/:id/stream", RunStreamHandler())

	// Start server
	err = r.Run(address)
	if err != nil {
		return err
	}

	return
}
