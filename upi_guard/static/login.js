const form=document.querySelector('#login-form');
form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('button');button.disabled=true;
  const error=document.querySelector('#login-error');error.textContent='';
  try {
    const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Sign-in failed');
    window.location.assign('/');
  } catch(exc){error.textContent=exc.message;} finally{button.disabled=false;}
});
