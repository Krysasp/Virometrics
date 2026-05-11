/**
 * SSEHandler - Server-Sent Events client for real-time streaming.
 * Handles connection, event parsing, reconnection, and error handling.
 */
class SSEHandler {
    /**
     * @param {string} url - SSE endpoint URL
     * @param {object} options - Configuration options
     */
    constructor(url, options = {}) {
        this.url = url;
        this.handlers = {};
        this.eventSource = null;
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.maxRetries = options.maxRetries || 5;
        this.retryCount = 0;
        this.reconnectTimer = null;
        this.isIntentionalClose = false;
    }

    /**
     * Register an event handler.
     * @param {string} event - Event name ('message', 'status', 'stdout', etc.)
     * @param {function} callback - Callback(data, event)
     */
    on(event, callback) {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event].push(callback);
    }

    /**
     * Connect to the SSE endpoint.
     */
    connect() {
        this.isIntentionalClose = false;
        this._doConnect();
    }

    _doConnect() {
        try {
            this.eventSource = new EventSource(this.url);

            // Handle default 'message' events
            this.eventSource.onmessage = (e) => {
                this._handleEvent('message', e);
            };

            // Handle named events
            Object.keys(this.handlers).forEach(event => {
                if (event === 'message') return; // Already handled
                this.eventSource.addEventListener(event, (e) => {
                    this._handleEvent(event, e);
                });
            });

            this.eventSource.onopen = () => {
                this.retryCount = 0; // Reset on successful connection
                this._trigger('open', null);
            };

            this.eventSource.onerror = (e) => {
                this._handleError(e);
            };
        } catch (err) {
            console.error('SSE connection error:', err);
            this._scheduleReconnect();
        }
    }

    _handleEvent(event, e) {
        const handlers = this.handlers[event] || [];
        try {
            const data = JSON.parse(e.data);
            handlers.forEach(callback => callback(data, e));
        } catch (err) {
            // If not JSON, pass raw string
            handlers.forEach(callback => callback(e.data, e));
        }
    }

    _handleError(e) {
        if (!this.eventSource) return;

        if (this.eventSource.readyState === EventSource.CLOSED) {
            this._trigger('close', null);
            if (!this.isIntentionalClose) {
                this._scheduleReconnect();
            }
            return;
        }

        if (this.eventSource.readyState === EventSource.CONNECTING) {
            this._trigger('reconnecting', null);
        }
    }

    _scheduleReconnect() {
        if (this.retryCount >= this.maxRetries) {
            console.warn('SSE: Max retries reached, giving up');
            this._trigger('max_retries', null);
            return;
        }

        this.retryCount++;
        this._trigger('reconnect', { attempt: this.retryCount });

        this.reconnectTimer = setTimeout(() => {
            this._doConnect();
        }, this.reconnectDelay);
    }

    _trigger(event, data) {
        const handlers = this.handlers[event] || [];
        handlers.forEach(callback => callback(data, null));
    }

    /**
     * Disconnect from the SSE endpoint.
     */
    disconnect() {
        this.isIntentionalClose = true;

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}
