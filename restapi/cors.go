package restapi

import (
	"os"

	"github.com/gin-gonic/gin"
)

// CORSMiddleware adds CORS headers to each response and handles OPTIONS requests
// It is enabled when the environment variable ENABLE_CORS is set to "true".
// Allowed origin is read from FABRIC_ALLOW_ORIGIN (defaults to "*").
func CORSMiddleware() gin.HandlerFunc {
	enabled := os.Getenv("ENABLE_CORS") == "true"
	allowedOrigin := os.Getenv("FABRIC_ALLOW_ORIGIN")
	if allowedOrigin == "" {
		allowedOrigin = "*"
	}

	return func(c *gin.Context) {
		if !enabled {
			c.Next()
			return
		}

		c.Writer.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}
