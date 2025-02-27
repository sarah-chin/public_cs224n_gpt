import torch

from einops import rearrange
from torch import nn


class CausalSelfAttention(nn.Module):
  def __init__(self, config):
    super().__init__()

    self.num_attention_heads = config.num_attention_heads
    self.attention_head_size = int(config.hidden_size / config.num_attention_heads)
    self.all_head_size = self.num_attention_heads * self.attention_head_size

    # Initialize the linear transformation layers for key, value, query.
    self.query = nn.Linear(config.hidden_size, self.all_head_size)
    self.key = nn.Linear(config.hidden_size, self.all_head_size)
    self.value = nn.Linear(config.hidden_size, self.all_head_size)
    # This dropout is applied to normalized attention scores following the original
    # implementation of transformer. Although it is a bit unusual, we empirically
    # observe that it yields better performance.
    self.dropout = nn.Dropout(config.attention_probs_dropout_prob)

  def transform(self, x, linear_layer):
    # The corresponding linear_layer of k, v, q are used to project the hidden_state (x).
    proj = linear_layer(x)
    # Next, we need to produce multiple heads for the proj. This is done by spliting the
    # hidden state to self.num_attention_heads, each of size self.attention_head_size.
    proj = rearrange(proj, 'b t (h d) -> b t h d', h=self.num_attention_heads)
    # By proper transpose, we have proj of size [bs, num_attention_heads, seq_len, attention_head_size].
    proj = rearrange(proj, 'b t h d -> b h t d')
    return proj

  def attention(self, key, query, value, attention_mask):

    ### YOUR CODE HERE

    # input vectors of size [batch size, num_attention_heads, seq_len, attention_head_size]
    b, h, t, d = key.size()

    # attention(query, key, value) = softmax(qkt/sqrt(dk))V

    # compute attention scores s = QKT
    attention_scores = torch.matmul(query, key.transpose(-1, -2)) # shape (b, h, seq_len, seq_len)

    # scale scores by sqrt dk
    attention_scores = attention_scores / (d**0.5) # shape (b, h, seq_len, attn_head_size)

    # apply upper triangular mask (torch.triu) to attention weights before the softmax
    mask = torch.triu(torch.full((t, t), float('-inf'), device=query.device), diagonal=1) # shape (T, T)
    mask = mask.unsqueeze(0).unsqueeze(0) # shape (1, 1, T, T)
    attention_scores += mask

    if attention_mask is not None:
      attention_mask = attention_mask.to(dtype=attention_scores.dtype) 
      # attention_mask *= float('-inf')
      # attention_scores += attention_mask
      attention_mask = attention_mask.masked_fill(attention_mask == -10000, float('-inf'))
      attention_scores += attention_mask
      # attention_scores = attention_scores.masked_fill(attention_mask == 0, float('-inf'))

    # apply softmax across key
    attention_prob_dist = nn.functional.softmax(attention_scores, dim=-1)
    attention_prob_dist = self.dropout(attention_prob_dist)

    # output = A*V
    output = torch.matmul(attention_prob_dist, value) # shape (b, h, seq_len, attn_head_size)

    # back to original shape (b, seq_len, hidden_size = h * attn_head_size)
    output = torch.reshape(output, (b, t, -1))

    return output


  def forward(self, hidden_states, attention_mask):
    """
    hidden_states: [bs, seq_len, hidden_state]
    attention_mask: [bs, 1, 1, seq_len]
    output: [bs, seq_len, hidden_state]
    """
    # First, we have to generate the key, value, query for each token for multi-head attention
    # using self.transform (more details inside the function).
    # Size of *_layer is [bs, num_attention_heads, seq_len, attention_head_size].
    key_layer = self.transform(hidden_states, self.key)
    value_layer = self.transform(hidden_states, self.value)
    query_layer = self.transform(hidden_states, self.query)
    
    # Calculate the multi-head attention.
    attn_value = self.attention(key_layer, query_layer, value_layer, attention_mask)
    return attn_value
