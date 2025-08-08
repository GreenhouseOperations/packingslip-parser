import React, { useState } from 'react';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type === 'application/pdf') {
      setFile(droppedFile);
    } else {
      alert('Please drop a PDF file');
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleFileInput = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile && selectedFile.type === 'application/pdf') {
      setFile(selectedFile);
    } else {
      alert('Please select a PDF file');
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/upload', { 
        method: 'POST', 
        body: formData 
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'packing_slips_v4.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (error) {
      alert('Error uploading file. Please try again.');
      console.error('Upload error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="logo">
            <div className="logo-text">Greenhouse Operations</div>
          </div>
        </div>
      </header>

      <div className="container">
        <div className="hero-section">
          <h1>Packing Slip Parser</h1>
          <p className="subtitle">Convert PDF packing slips to structured CSV data</p>
          <p className="description">
            Upload your PDF packing slip and receive a properly formatted CSV file for your operations system.
          </p>
        </div>
        
        <div className="upload-section">
          <div 
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {file ? (
              <div className="file-info">
                <p>📄 {file.name}</p>
                <p className="file-size">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : (
              <div className="drop-message">
                <p>Drop your PDF file here</p>
                <p className="or-text">or</p>
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handleFileInput}
                  id="file-input"
                  style={{ display: 'none' }}
                />
                <label htmlFor="file-input" className="file-button">
                  Choose File
                </label>
              </div>
            )}
          </div>

          <div className="actions">
            <button 
              onClick={handleUpload} 
              disabled={!file || isLoading}
              className="primary-button"
            >
              {isLoading ? (
                <>
                  <div className="loading-spinner"></div>
                  Processing
                </>
              ) : (
                'Generate CSV'
              )}
            </button>
            
            {file && (
              <button 
                onClick={() => setFile(null)}
                className="secondary-button"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
