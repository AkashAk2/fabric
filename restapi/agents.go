package restapi

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/gin-gonic/gin"
)

// agnoProxy creates a reverse proxy to the Agno service
func agnoProxy() *httputil.ReverseProxy {
	target, _ := url.Parse("http://127.0.0.1:9000")
	proxy := httputil.NewSingleHostReverseProxy(target)
	return proxy
}

// OrchestrateHandler proxies POST /agents/orchestrate to POST /generate
func OrchestrateHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.URL.Path = "/generate"
		c.Request.Host = "127.0.0.1:9000"
		agnoProxy().ServeHTTP(c.Writer, c.Request)
	}
}

// RunStreamHandler proxies GET /agents/runs/{id}/stream to GET /v1/runs/{id}/stream
func RunStreamHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		runID := c.Param("id")
		if runID == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "run id required"})
			return
		}
		c.Request.URL.Path = "/v1/runs/" + runID + "/stream"
		c.Request.Host = "127.0.0.1:9000"
		// Set headers for SSE
		c.Writer.Header().Set("Cache-Control", "no-cache")
		c.Writer.Header().Set("Connection", "keep-alive")
		c.Writer.Header().Set("Content-Type", "text/event-stream")
		agnoProxy().ServeHTTP(c.Writer, c.Request)
	}
}

// FileProxyHandler proxies GET /agents/files/output.pptx to GET /download
func FileProxyHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.URL.Path = "/download"
		c.Request.Host = "127.0.0.1:9000"
		agnoProxy().ServeHTTP(c.Writer, c.Request)
	}
}
