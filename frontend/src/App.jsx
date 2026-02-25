import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SurveyCardTestPage from './pages/SurveyCardTestPage'
import InterviewPage from './pages/InterviewPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/survey-card-test" element={<SurveyCardTestPage />} />
      <Route path="/interview" element={<InterviewPage />} />
    </Routes>
  )
}

export default App
