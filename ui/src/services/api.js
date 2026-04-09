import axios from 'axios';

// 创建axios实例
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_OPENAI_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${import.meta.env.VITE_OPENAI_API_KEY}`
  }
});

// 发送聊天请求
export const sendChatRequest = async (messages) => {
  try {
    const response = await apiClient.post('/chat/completions', {
      model: import.meta.env.VITE_OPENAI_MODEL,
      messages,
      stream: true
    }, {
      responseType: 'stream'
    });
    
    return response;
  } catch (error) {
    console.error('Error sending chat request:', error);
    throw error;
  }
};

// 处理流式响应
export const handleStreamResponse = (response, onMessage, onError) => {
  const reader = response.data.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let doneReasoning = false;

  const processChunk = async () => {
    const { done, value } = await reader.read();
    
    if (done) {
      return;
    }

    buffer += decoder.decode(value, { stream: true });
    
    // 处理SSE格式的响应
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
  };

  processChunk();
};