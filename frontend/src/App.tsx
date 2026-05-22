import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { Search, GitBranch, BarChart2, AlertCircle } from 'lucide-react'
import SearchPage from './pages/SearchPage'
import TriagePage from './pages/TriagePage'
import AnalyticsPage from './pages/AnalyticsPage'

const NAV_ITEMS = [
  { to: '/',          label: 'Search',    icon: Search },
  { to: '/triage',    label: 'Triage',    icon: GitBranch },
  { to: '/analytics', label: 'Analytics', icon: BarChart2 },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        {/* Top nav */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-14">
              {/* Brand */}
              <div className="flex items-center gap-2">
                <AlertCircle className="w-6 h-6 text-blue-600" />
                <span className="font-semibold text-gray-900 text-sm">
                  Incident KB Assistant
                </span>
              </div>

              {/* Nav links */}
              <nav className="flex items-center gap-1">
                {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    className={({ isActive }) =>
                      `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ` +
                      (isActive
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100')
                    }
                  >
                    <Icon className="w-4 h-4" />
                    {label}
                  </NavLink>
                ))}
              </nav>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Routes>
            <Route path="/"          element={<SearchPage />} />
            <Route path="/triage"    element={<TriagePage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
