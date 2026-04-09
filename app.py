import os
import io
import zipfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from PIL import Image
import tempfile

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000"])

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_image(file):
    """Process individual image for PDF conversion"""
    img = Image.open(file.stream)
    
    # Convert RGBA to RGB (for PDF compatibility)
    if img.mode == 'RGBA':
        # Create white background for transparent images
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        rgb_img.paste(img, mask=img.split()[3])
        img = rgb_img
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Auto-rotate based on EXIF data
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except:
        pass
    
    return img

def generate_merged_pdf(images):
    """Generate a single PDF from multiple images"""
    pdf_buffer = io.BytesIO()
    processed_images = []
    
    for file in images:
        img = process_image(file)
        processed_images.append(img)
    
    if processed_images:
        processed_images[0].save(
            pdf_buffer,
            format='PDF',
            save_all=True,
            append_images=processed_images[1:],
            resolution=100.0,
            optimize=True
        )
    
    pdf_buffer.seek(0)
    return pdf_buffer

def generate_separate_pdfs(images):
    """Generate separate PDFs for each image and return as ZIP"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for idx, file in enumerate(images, 1):
            img = process_image(file)
            pdf_buffer = io.BytesIO()
            img.save(pdf_buffer, format='PDF', optimize=True)
            pdf_buffer.seek(0)
            
            # Generate filename for individual PDF
            timestamp = datetime.now().strftime('%Y-%m-%d')
            filename = f'image-{idx}-{timestamp}.pdf'
            zip_file.writestr(filename, pdf_buffer.getvalue())
    
    zip_buffer.seek(0)
    return zip_buffer

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'version': '2.0.0'}), 200

@app.route('/convert-to-pdf', methods=['POST'])
def convert_to_pdf():
    """
    Convert images to PDF(s) based on mode
    Request: multipart/form-data with 'images' and 'mode' (merge/separate)
    """
    try:
        # Check if images were uploaded
        if 'images' not in request.files:
            return jsonify({'error': 'No images uploaded'}), 400
        
        files = request.files.getlist('images')
        mode = request.form.get('mode', 'merge')
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No images selected'}), 400
        
        # Validate all files
        for file in files:
            if not allowed_file(file.filename):
                return jsonify({'error': f'Invalid file type: {file.filename}. Allowed: PNG, JPG, JPEG, WEBP'}), 400
        
        if mode == 'separate':
            # Generate separate PDFs as ZIP
            zip_buffer = generate_separate_pdfs(files)
            timestamp = datetime.now().strftime('%Y-%m-%d')
            filename = f'pdfs_{timestamp}.zip'
            
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=filename
            )
        else:
            # Merge all into single PDF
            pdf_buffer = generate_merged_pdf(files)
            timestamp = datetime.now().strftime('%Y-%m-%d-%H%M')
            filename = f'image-pdf-{timestamp}.pdf'
            
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )
    
    except Exception as e:
        app.logger.error(f'Error converting images: {str(e)}')
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

@app.route('/validate-images', methods=['POST'])
def validate_images():
    """Validate images before upload"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'No images uploaded'}), 400
        
        files = request.files.getlist('images')
        validation_results = []
        
        for file in files:
            is_valid = allowed_file(file.filename)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            is_size_valid = size <= MAX_FILE_SIZE
            
            validation_results.append({
                'filename': file.filename,
                'valid': is_valid and is_size_valid,
                'error': None if (is_valid and is_size_valid) else 
                        ('Invalid type' if not is_valid else 'File too large (>10MB)')
            })
        
        return jsonify({'results': validation_results}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')