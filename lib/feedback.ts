import { postFeedback as sendFeedback } from '@/lib/api'
import { reportFeedback } from '@/lib/brain'

/**
 * Teach the brain: -1 skip, +1 listen-through, 0 neutral. The backend response
 * carries the updated /brain_state; publishing it lets the Mushroom Body view
 * pulse on the cells that moved and refetch the current song's state right away.
 */
export function postFeedback(trackId: string, reward: -1 | 0 | 1) {
  return sendFeedback(trackId, reward).then((response) => {
    // A neutral reward counts no signal and changes no weights, so it gets no pulse.
    if (reward !== 0) reportFeedback(response.brain_state)
  })
}
