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

    const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'parsed_data.csv';
        if (contentDisposition && contentDisposition.indexOf('attachment') !== -1) {
          const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
          const matches = filenameRegex.exec(contentDisposition);
          if (matches != null && matches[1]) {
            filename = matches[1].replace(/['"]/g, '');
          }
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      } else {
        console.error('Response not ok:', response.status, response.statusText);
        const errorText = await response.text();
        console.error('Error response body:', errorText);
        alert(`Error: ${response.status} - ${response.statusText}`);
      }
    } catch (error) {
      console.error('Upload error details:', error);
      alert(`Error uploading file: ${error.message}. Please try again.`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="container">
        <div className="hero-section">
          <h1>Document Parser</h1>
          <p className="subtitle">Convert PDF packing slips and sales orders to structured CSV data</p>
          <p className="description">
            Upload your PDF packing slip or sales order and receive a properly formatted CSV file for your operations system.
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

      {/* Watermark */}
      <div className="watermark">
        Made by Dawang
      </div>
    </div>
  );
}

export default App;
