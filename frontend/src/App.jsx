import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SurveyCardTestPage from './pages/SurveyCardTestPage'
import InterviewPage from './pages/InterviewPage'
import GraphView from './pages/GraphView'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/survey-card-test" element={<SurveyCardTestPage />} />
      <Route path="/interview" element={<InterviewPage />} />
      <Route path="/tasks/:id/graph" element={<GraphView />} />
    </Routes>
  )
}

export default App
