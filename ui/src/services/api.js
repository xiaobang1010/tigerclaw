import axios from 'axios';

export const sendChatRequest = async (messages, sessionId = '') => {
  const headers = {
    'Content-Type': 'application/json',
  };
  const body = JSON.stringify({
    model: '',
    messages,
    stream: true,
    session_id: sessionId
  });

  try {
    const response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers,
      cache: 'no-store',
      body
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API error: ${response.status} - ${errorText}`);
    }

    return response;
  } catch (error) {
    console.error('[sendChatRequest] fetch failed:', error.name, error.message);
    throw error;
  }
};

export const handleStreamResponse = (response, onMessage, onError) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let doneReasoning = false;

  const processChunk = async () => {
    try {
      const { done, value } = await reader.read();

      if (done) {
        return;
      }

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line === '') continue;
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            return;
          }
          try {
            const chunk = JSON.parse(data);
            if (chunk.choices && chunk.choices[0]) {
              const reasoningChunk = chunk.choices[0].delta.reasoning_content;
              const answerChunk = chunk.choices[0].delta.content;

              if (reasoningChunk) {
                onMessage(reasoningChunk, 'reasoning');
              } else if (answerChunk) {
                if (!doneReasoning) {
                  onMessage('\n\n === Final Answer ===\n', 'system');
                  doneReasoning = true;
                }
                onMessage(answerChunk, 'answer');
              }
            }
          } catch (error) {
            console.error('Error parsing chunk:', error);
            onError(error);
          }
        }
      }

      processChunk();
    } catch (error) {
      onError(error);
    }
  };

  processChunk();
};

const traceClient = axios.create({
  headers: {
    'Content-Type': 'application/json'
  }
});

export const fetchTraces = async (params = {}) => {
  const response = await traceClient.get('/api/v1/traces', { params });
  return response.data;
};

export const fetchTraceDetail = async (traceId) => {
  const response = await traceClient.get(`/api/v1/traces/${traceId}`);
  return response.data;
};

export const fetchTraceStats = async () => {
  const response = await traceClient.get('/api/v1/traces/stats');
  return response.data;
};
