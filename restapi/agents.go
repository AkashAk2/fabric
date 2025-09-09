

package restapi

import (
	"context"
	"errors"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// OrchestrateStreamHandler proxies POST /agents/generate-stream to POST /generate-stream
func OrchestrateStreamHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.URL.Path = "/generate-stream"
	serveProxyWithRecover(c)
	}
}

// agnoProxy creates a reverse proxy to the Agno service
func agnoProxy() *httputil.ReverseProxy {
	return getAgnoProxy()
}

// OrchestrateHandler proxies POST /agents/orchestrate to POST /generate
func OrchestrateHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.URL.Path = "/generate"
	serveProxyWithRecover(c)
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
	// Agno exposes /runs/{id}/stream
	c.Request.URL.Path = "/runs/" + runID + "/stream"
	// Set headers for SSE (proxy will pass upstream headers too)
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("Content-Type", "text/event-stream")
	c.Writer.Header().Set("X-Accel-Buffering", "no")
	serveProxyWithRecover(c)
	}
}

// FileProxyHandler proxies GET /agents/files/output.pptx to GET /download
func FileProxyHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.URL.Path = "/download"
	serveProxyWithRecover(c)
	}
}

var (
	agnoProxyOnce sync.Once
	cachedAgnoRP  *httputil.ReverseProxy
)

func getAgnoProxy() *httputil.ReverseProxy {
	agnoProxyOnce.Do(func() {
		target, _ := url.Parse("http://127.0.0.1:9000")
		rp := httputil.NewSingleHostReverseProxy(target)

		// Preserve the original director, then extend it
		origDirector := rp.Director
		rp.Director = func(req *http.Request) {
			origDirector(req)
			// Ensure Host and scheme match target
			req.Host = target.Host
			req.URL.Host = target.Host
			req.URL.Scheme = target.Scheme
			// Disable compression to keep SSE streaming unbuffered
			req.Header.Del("Accept-Encoding")
			req.Header.Set("Connection", "keep-alive")
		}

		// Flush small chunks frequently for SSE
		rp.FlushInterval = 100 * time.Millisecond

		// Gracefully handle client disconnects and proxy errors
		rp.ErrorHandler = func(rw http.ResponseWriter, req *http.Request, err error) {
			if err == nil {
				return
			}
			msg := strings.ToLower(err.Error())
			// Ignore common SSE disconnect/abort cases
			if errors.Is(err, context.Canceled) ||
				strings.Contains(msg, "context canceled") ||
				strings.Contains(msg, "http: abort handler") ||
				strings.Contains(msg, "broken pipe") ||
				strings.Contains(msg, "connection reset") ||
				strings.Contains(msg, "use of closed network connection") ||
				strings.Contains(msg, "headers were already written") ||
				strings.Contains(msg, "write on closed") {
				return
			}
			// Only write an error if we haven't started streaming
			http.Error(rw, "proxy error: "+err.Error(), http.StatusBadGateway)
		}

		// Transport with compression disabled (helps SSE)
		rp.Transport = &http.Transport{
			Proxy:               http.ProxyFromEnvironment,
			ForceAttemptHTTP2:   false,
			DisableCompression:  true,
		}

		cachedAgnoRP = rp
	})
	return cachedAgnoRP
}

// serveProxyWithRecover calls the reverse proxy and swallows expected abort panics
// that occur when clients close SSE/EventSource connections.
func serveProxyWithRecover(c *gin.Context) {
	defer func() {
		if r := recover(); r != nil {
			// Ignore standard abort/cancel panics
			if r == http.ErrAbortHandler {
				return
			}
			if err, ok := r.(error); ok {
				msg := strings.ToLower(err.Error())
				if strings.Contains(msg, "broken pipe") || strings.Contains(msg, "connection reset") || strings.Contains(msg, "context canceled") {
					return
				}
			}
			// Re-panic unexpected errors
			panic(r)
		}
	}()
	agnoProxy().ServeHTTP(c.Writer, c.Request)
}
