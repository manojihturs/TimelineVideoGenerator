import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { UploadPage } from './pages/UploadPage'
import { MappingPage } from './pages/MappingPage'
import { StudioPage } from './pages/StudioPage'

function App() {
  return (
    <div className="min-h-screen bg-[#0b0f14]">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/mapping/:datasetId" element={<MappingPage />} />
          <Route path="/studio/:datasetId" element={<StudioPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  )
}

export default App
