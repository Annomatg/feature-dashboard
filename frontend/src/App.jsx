import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SurveyCardTestPage from './pages/SurveyCardTestPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/survey-card-test" element={<SurveyCardTestPage />} />
    </Routes>
  )
}

export default App
