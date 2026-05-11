"""Server-Sent Events (SSE) streaming for Virometrics.

Provides real-time streaming of tool execution output to web clients.
Formats events according to the SSE specification.
"""

import time
import json
import logging
from typing import Generator, Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 15


class SSEStream:
    """Generate Server-Sent Events for real-time output streaming."""

    def __init__(self, executor, execution_id: int):
        self.executor = executor
        self.execution_id = execution_id
        self.last_sequence = -1
        self.last_heartbeat = time.time()

    def format_event(self, event_type: str, data: Any, event_id: Optional[str] = None) -> str:
        """Format a single SSE event."""
        lines = []
        if event_id:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {event_type}")
        if isinstance(data, str):
            lines.append(f"data: {data}")
        else:
            lines.append(f"data: {json.dumps(data)}")
        lines.append("")  # Blank line signals end of event
        return "\n".join(lines) + "\n"

    def stream(self) -> Generator[str, None, None]:
        """
        Generate SSE events for this execution.
        Yields formatted SSE strings.
        """
        # Send initial status
        status = self.executor.get_status(self.execution_id)
        if status:
            yield self.format_event('status', status)

        # Send existing outputs first
        outputs = self.executor.get_new_outputs(self.execution_id, -1)
        for output in outputs:
            yield self.format_event(output['type'], {
                'content': output['content'],
                'sequence': output['sequence'],
                'timestamp': output['timestamp']
            })
            self.last_sequence = max(self.last_sequence, output['sequence'])

        # Poll for new outputs
        while True:
            try:
                # Check if execution is still running
                status = self.executor.get_status(self.execution_id)
                if not status:
                    yield self.format_event('error', {'message': 'Execution not found'})
                    break

                # Send status update
                yield self.format_event('status', status)

                # Get new outputs
                new_outputs = self.executor.get_new_outputs(
                    self.execution_id, self.last_sequence
                )

                for output in new_outputs:
                    yield self.format_event(output['type'], {
                        'content': output['content'],
                        'sequence': output['sequence'],
                        'timestamp': output['timestamp']
                    })
                    self.last_sequence = output['sequence']

                # Check if completed
                if status['status'] in ('completed', 'failed', 'cancelled'):
                    yield self.format_event('complete', status)
                    break

                # Send heartbeat if needed
                now = time.time()
                if now - self.last_heartbeat > HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    self.last_heartbeat = now

                # Small delay before next poll
                time.sleep(0.5)

            except GeneratorExit:
                logger.info(f"SSE stream closed by client for execution {self.execution_id}")
                break
            except Exception as e:
                logger.error(f"SSE stream error for execution {self.execution_id}: {e}")
                yield self.format_event('error', {'message': str(e)})
                break


def create_sse_response(stream_generator, max_age=0):
    """Create a Flask Response for SSE streaming."""
    from flask import Response

    def generate():
        yield ": connected\n\n"
        for event in stream_generator():
            yield event

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable Nginx buffering
        }
    )
