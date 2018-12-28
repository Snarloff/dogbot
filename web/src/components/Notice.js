import styled from 'styled-components'

const MOODS = {
  default: ['hsl(220, 100%, 85%)', 'hsl(220, 100%, 95%)'],
  danger: ['hsl(0, 100%, 85%)', 'hsl(0, 100%, 95%)'],
  success: ['hsl(120, 100%, 75%)', 'hsl(120, 100%, 95%)'],
}

const Notice = styled.div`
  padding: 0.5em 1em;
  border: solid 1px ${({ mood = 'default' }) => MOODS[mood][0]};
  background: ${({ mood = 'default' }) => MOODS[mood][1]};
  border-radius: 0.15rem;
  margin: 1rem 0;
`

export default Notice
